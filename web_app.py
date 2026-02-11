import asyncio
import contextlib
import csv
import json
import logging
import os
import time
import hashlib
import io
from typing import Dict, Optional, List, Any, Tuple

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect, UploadFile, File
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.websockets import WebSocketState

from config import get_env, get_env_bool, load_dotenv
from logging_utils import configure_logging, log_event, mask_secret
from sarvam_llm_service import SarvamLLMService
from sarvam_stt_service import SaarikaSTTService
from web_session import WebCallSession
from audit_store import SQLiteAuditStore
from excel_source import ExcelCustomerSource
from excel_sink import ExcelOutcomeSink
from actions import ActionRouter
from knowledge_store import SQLiteFTSKnowledgeStore
from strategy_engine import StrategyEngine
from compliance_engine import ComplianceEngine
from campaign_service import CampaignService
from followup_service import FollowupService
from integrations.crm_adapter import CRMAdapter
from portfolio_service import PortfolioService
from workbench_service import WorkbenchService
from alerts_service import AlertsService
from reports_service import ReportsService
from sync_service import SyncService

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(__file__)
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")
DATA_DIR = os.path.join(BASE_DIR, "data")
KNOWLEDGE_DIR_DEFAULT = os.path.join(BASE_DIR, "knowledge")

app = FastAPI()


@app.middleware("http")
async def https_redirect(request: Request, call_next):
    """Redirect HTTP to HTTPS on Azure App Service (or any reverse proxy that sets X-Forwarded-Proto)."""
    proto = request.headers.get("x-forwarded-proto", "")
    host = request.headers.get("host", "")
    if proto == "http" and host and "localhost" not in host and "127.0.0.1" not in host:
        url = request.url.replace(scheme="https")
        return RedirectResponse(url, status_code=301)
    return await call_next(request)


app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

# Global singletons for the demo server process.
_demo_state: Dict[str, object] = {}
_report_scheduler_task: Optional[asyncio.Task] = None


def _file_token(path: str) -> str:
    try:
        st = os.stat(path)
        raw = f"{path}:{st.st_mtime_ns}:{st.st_size}".encode("utf-8")
        return hashlib.sha1(raw).hexdigest()[:10]
    except Exception:
        return "dev"


def _build_info_payload() -> Dict[str, Any]:
    admin_js = os.path.join(FRONTEND_DIR, "admin.js")
    app_js = os.path.join(FRONTEND_DIR, "app.js")
    styles_css = os.path.join(FRONTEND_DIR, "styles.css")
    t1 = _file_token(admin_js)
    t2 = _file_token(app_js)
    t3 = _file_token(styles_css)
    static_token = hashlib.sha1(f"{t1}|{t2}|{t3}".encode("utf-8")).hexdigest()[:10]
    return {
        "app": "collections-agent",
        "static_token": static_token,
        "admin_js_token": t1,
        "app_js_token": t2,
        "styles_token": t3,
        "demo_mode": get_env_bool("DEMO_MODE", True),
        "pilot_mode": get_env_bool("PILOT_MODE", False),
        "timestamp": int(time.time()),
    }


def _render_html(path: str, *, no_store: bool = False) -> HTMLResponse:
    with open(path, "r", encoding="utf-8") as handle:
        html = handle.read()
    build = _build_info_payload()
    token = str(build.get("static_token") or "dev")
    html = html.replace("__STATIC_VER__", token)
    html = html.replace("__BUILD_TOKEN__", token)
    headers = {}
    if no_store:
        headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        headers["Pragma"] = "no-cache"
    return HTMLResponse(html, headers=headers)


def _role_tokens() -> Dict[str, str]:
    out: Dict[str, str] = {}
    raw = get_env("ROLE_TOKENS_JSON")
    if raw:
        try:
            data = json.loads(raw)
            if isinstance(data, dict):
                for token, role in data.items():
                    if token and role:
                        out[str(token)] = str(role).upper()
        except Exception:
            pass
    admin_token = get_env("ADMIN_TOKEN")
    if admin_token and admin_token not in out:
        out[admin_token] = "ADMIN"
    return out


def _get_role(request: Request) -> str:
    auth = (request.headers.get("authorization") or "").strip()
    token = ""
    if auth.lower().startswith("bearer "):
        token = auth[7:].strip()
    if not token:
        token = (request.headers.get("x-admin-token") or "").strip()
    role = _role_tokens().get(token)
    return role or "VIEWER"


def _require_role(request: Request, allowed: Tuple[str, ...]) -> Optional[JSONResponse]:
    role = _get_role(request)
    if role in allowed:
        return None
    return JSONResponse({"error": "forbidden", "required_roles": list(allowed), "current_role": role}, status_code=403)


def _actor(request: Request) -> str:
    actor = (request.headers.get("x-user") or "").strip()
    if actor:
        return actor
    role = _get_role(request)
    return f"{role.lower()}_user"


def _pagination(request: Request) -> Tuple[int, int]:
    try:
        page = int(request.query_params.get("page") or 1)
    except Exception:
        page = 1
    try:
        page_size = int(request.query_params.get("page_size") or 25)
    except Exception:
        page_size = 25
    return max(1, page), max(1, min(100, page_size))


@app.get("/")
async def index() -> HTMLResponse:
    index_path = os.path.join(FRONTEND_DIR, "index.html")
    return _render_html(index_path, no_store=False)

@app.get("/admin")
async def admin() -> HTMLResponse:
    admin_path = os.path.join(FRONTEND_DIR, "admin.html")
    return _render_html(admin_path, no_store=True)


@app.get("/api/system/build_info")
async def api_build_info(request: Request):
    return _build_info_payload()


def _require_admin(request) -> Optional[JSONResponse]:
    return _require_role(request, ("ADMIN", "SUPERVISOR"))


def _get_demo_singletons() -> Dict[str, object]:
    if _demo_state:
        return _demo_state

    os.makedirs(DATA_DIR, exist_ok=True)
    customers_path = get_env("CUSTOMERS_XLSX_PATH", os.path.join(DATA_DIR, "customers.xlsx"))
    output_path = get_env("DEMO_OUTPUT_XLSX_PATH", os.path.join(DATA_DIR, "demo_output.xlsx"))
    db_path = get_env("DEMO_DB_PATH", os.path.join(DATA_DIR, "demo.db"))
    knowledge_dir = get_env("KNOWLEDGE_DIR", KNOWLEDGE_DIR_DEFAULT)
    pay_base_url = get_env("DEMO_PAY_BASE_URL", "https://pay.example/demo")

    retention_days = int(get_env("PHI_RETENTION_DAYS", "30") or "30")
    metrics_tz = get_env("METRICS_TIMEZONE", "Asia/Kolkata") or "Asia/Kolkata"

    audit = SQLiteAuditStore(db_path, retention_days=retention_days, metrics_tz=metrics_tz)
    sink = ExcelOutcomeSink(output_path)
    sink.ensure_workbook()
    source = ExcelCustomerSource(customers_path)
    router = ActionRouter(pay_base_url=pay_base_url)
    knowledge = SQLiteFTSKnowledgeStore(db_path, knowledge_dir)
    strategy = StrategyEngine()
    compliance = ComplianceEngine()
    campaign_service = CampaignService(db_path)
    followups = FollowupService(db_path, tz_name=metrics_tz)
    crm = CRMAdapter(db_path)
    portfolio = PortfolioService(db_path, DATA_DIR)
    workbench = WorkbenchService(db_path)
    alerts = AlertsService(db_path)
    reports = ReportsService(db_path, DATA_DIR, tz_name=metrics_tz)
    sync = SyncService(db_path)
    # Best-effort reindex on startup for demos (fast for small docs).
    try:
        knowledge.reindex()
    except Exception as exc:
        log_event(logger, "knowledge_reindex_startup_error", error=str(exc))

    _demo_state.update(
        {
            "audit": audit,
            "sink": sink,
            "source": source,
            "router": router,
            "knowledge": knowledge,
            "strategy": strategy,
            "compliance": compliance,
            "campaign_service": campaign_service,
            "followups": followups,
            "crm": crm,
            "portfolio": portfolio,
            "workbench": workbench,
            "alerts": alerts,
            "reports": reports,
            "sync": sync,
            "campaign_tasks": {},
            "sessions": {},  # session_id -> snapshot dict
            "session_objs": {},  # session_id -> WebCallSession
        }
    )
    _start_background_loops()
    return _demo_state


def _start_background_loops() -> None:
    global _report_scheduler_task
    if _report_scheduler_task and not _report_scheduler_task.done():
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    _report_scheduler_task = loop.create_task(_background_tick_loop(), name="ops_background_tick")


async def _background_tick_loop() -> None:
    while True:
        try:
            demo = _get_demo_singletons()
            reports: ReportsService = demo["reports"]  # type: ignore[assignment]
            alerts: AlertsService = demo["alerts"]  # type: ignore[assignment]
            followups: FollowupService = demo["followups"]  # type: ignore[assignment]
            audit: SQLiteAuditStore = demo["audit"]  # type: ignore[assignment]

            due = followups.due_followups(limit=300)
            for row in due:
                try:
                    reminder_type = str(row.get("reminder_type") or "")
                    status = "missed" if reminder_type == "ptp_t_plus_1_miss" else "sent"
                    followups.mark_status(str(row["idempotency_key"]), status=status)
                    audit.record_event(
                        event_type="followup_" + status,
                        session_id=str(row.get("session_id") or ""),
                        payload={
                            "reminder_type": reminder_type,
                            "idempotency_key": row.get("idempotency_key"),
                            "channel": row.get("channel"),
                        },
                    )
                except Exception as exc:
                    log_event(logger, "followup_background_error", error=str(exc))
            with contextlib.suppress(Exception):
                alerts.evaluate()
            with contextlib.suppress(Exception):
                reports.run_scheduler_tick()
        except Exception as exc:
            log_event(logger, "background_tick_error", error=str(exc))
        await asyncio.sleep(30.0)


async def _campaign_run_loop(campaign_id: str) -> None:
    demo = _get_demo_singletons()
    campaign_service: CampaignService = demo["campaign_service"]  # type: ignore[assignment]
    tasks: Dict[str, asyncio.Task] = demo["campaign_tasks"]  # type: ignore[assignment]
    try:
        for _ in range(1200):  # bounded loop to avoid runaway background task
            meta = campaign_service.get_campaign(campaign_id)
            if not meta or meta.get("status") not in {"active", "created"}:
                return
            result = campaign_service.run_pending_batch(campaign_id)
            if int(result.get("processed", 0)) <= 0:
                await asyncio.sleep(0.2)
            else:
                await asyncio.sleep(0.02)
            meta = campaign_service.get_campaign(campaign_id)
            if meta and meta.get("status") == "completed":
                return
    finally:
        tasks.pop(campaign_id, None)


@app.get("/api/metrics")
async def api_metrics(request: Request):
    deny = _require_role(request, ("ADMIN", "SUPERVISOR", "VIEWER"))
    if deny:
        return deny
    demo = _get_demo_singletons()
    audit: SQLiteAuditStore = demo["audit"]  # type: ignore[assignment]
    followups: FollowupService = demo["followups"]  # type: ignore[assignment]
    crm: CRMAdapter = demo["crm"]  # type: ignore[assignment]
    alerts: AlertsService = demo["alerts"]  # type: ignore[assignment]
    reports: ReportsService = demo["reports"]  # type: ignore[assignment]
    campaign_id = (request.query_params.get("campaign_id") or "").strip() or None
    # Tick background simulation services during dashboard refresh.
    due = followups.due_followups(limit=100)
    for row in due:
        try:
            reminder_type = str(row.get("reminder_type") or "")
            status = "missed" if reminder_type == "ptp_t_plus_1_miss" else "sent"
            audit.record_event(
                event_type=f"followup_{status}",
                session_id=str(row.get("session_id") or ""),
                payload={
                    "reminder_type": reminder_type,
                    "channel": row.get("channel"),
                    "phone": row.get("phone"),
                    "idempotency_key": row.get("idempotency_key"),
                },
            )
            followups.mark_status(str(row["idempotency_key"]), status=status)
        except Exception as exc:
            log_event(logger, "followup_send_tick_error", error=str(exc))
    crm_result = crm.process_queue(limit=120)
    alert_result = alerts.evaluate()
    report_result = reports.run_scheduler_tick()
    data = audit.metrics(campaign_id=campaign_id)
    data["followups_due_processed"] = len(due)
    data["outbound_tick"] = crm_result
    data["outbound_status"] = crm.status()
    data["alerts_tick"] = alert_result
    data["reports_tick"] = report_result
    data["build_info"] = _build_info_payload()
    return data

@app.get("/api/customers")
async def api_customers(request: Request):
    demo = _get_demo_singletons()
    source: ExcelCustomerSource = demo["source"]  # type: ignore[assignment]
    try:
        rows = source.list_customers()
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)
    return {"rows": rows}


@app.post("/api/portfolio/upload")
async def api_portfolio_upload(request: Request, file: UploadFile = File(...)):
    deny = _require_role(request, ("ADMIN", "SUPERVISOR"))
    if deny:
        return deny
    demo = _get_demo_singletons()
    portfolio: PortfolioService = demo["portfolio"]  # type: ignore[assignment]
    if not file.filename:
        return JSONResponse({"error": "filename_required"}, status_code=400)
    content = await file.read()
    try:
        result = portfolio.upload(filename=file.filename, content=content)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    return {"ok": True, **result}


@app.post("/api/portfolio/{upload_id}/map")
async def api_portfolio_map(upload_id: str, request: Request):
    deny = _require_role(request, ("ADMIN", "SUPERVISOR"))
    if deny:
        return deny
    demo = _get_demo_singletons()
    portfolio: PortfolioService = demo["portfolio"]  # type: ignore[assignment]
    try:
        body = await request.json()
    except Exception:
        body = {}
    mappings = body.get("mappings") if isinstance(body.get("mappings"), dict) else {}
    portfolio_name = str(body.get("portfolio_name") or f"Portfolio {upload_id}")
    try:
        result = portfolio.map_columns(upload_id=upload_id, mappings=mappings, portfolio_name=portfolio_name)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    return {"ok": True, **result}


@app.post("/api/portfolio/{portfolio_id}/validate")
async def api_portfolio_validate(portfolio_id: str, request: Request):
    deny = _require_role(request, ("ADMIN", "SUPERVISOR"))
    if deny:
        return deny
    demo = _get_demo_singletons()
    portfolio: PortfolioService = demo["portfolio"]  # type: ignore[assignment]
    try:
        result = portfolio.validate(portfolio_id=portfolio_id)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    return {"ok": True, **result}


@app.get("/api/portfolio/{portfolio_id}/preview")
async def api_portfolio_preview(portfolio_id: str, request: Request):
    deny = _require_role(request, ("ADMIN", "SUPERVISOR", "VIEWER"))
    if deny:
        return deny
    demo = _get_demo_singletons()
    portfolio: PortfolioService = demo["portfolio"]  # type: ignore[assignment]
    try:
        limit = int(request.query_params.get("limit") or 20)
    except Exception:
        limit = 20
    rows = portfolio.preview(portfolio_id=portfolio_id, limit=limit)
    return {"rows": rows, "limit": max(1, limit)}


@app.get("/api/portfolio/{portfolio_id}/errors.csv")
async def api_portfolio_errors_csv(portfolio_id: str, request: Request):
    deny = _require_role(request, ("ADMIN", "SUPERVISOR", "VIEWER"))
    if deny:
        return deny
    demo = _get_demo_singletons()
    portfolio: PortfolioService = demo["portfolio"]  # type: ignore[assignment]
    path = portfolio.get_errors_csv_path(portfolio_id)
    if not path or not os.path.exists(path):
        return JSONResponse({"error": "errors_csv_not_found"}, status_code=404)
    return FileResponse(path, filename=f"{portfolio_id}-errors.csv")


@app.post("/api/portfolio/{portfolio_id}/exclusions/upload")
async def api_portfolio_exclusions_upload(portfolio_id: str, request: Request, file: UploadFile = File(...)):
    deny = _require_role(request, ("ADMIN", "SUPERVISOR"))
    if deny:
        return deny
    demo = _get_demo_singletons()
    portfolio: PortfolioService = demo["portfolio"]  # type: ignore[assignment]
    content = await file.read()
    try:
        out = portfolio.add_exclusions(portfolio_id=portfolio_id, filename=file.filename or "exclusions.csv", content=content)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    return {"ok": True, **out}


@app.post("/api/portfolio/{portfolio_id}/launch")
async def api_portfolio_launch(portfolio_id: str, request: Request):
    deny = _require_role(request, ("ADMIN", "SUPERVISOR"))
    if deny:
        return deny
    demo = _get_demo_singletons()
    portfolio: PortfolioService = demo["portfolio"]  # type: ignore[assignment]
    campaign_service: CampaignService = demo["campaign_service"]  # type: ignore[assignment]
    workbench: WorkbenchService = demo["workbench"]  # type: ignore[assignment]
    try:
        body = await request.json()
    except Exception:
        body = {}

    campaign_name = str(body.get("campaign_name") or f"Campaign {portfolio_id}")
    max_attempts = int(body.get("retry_policy", {}).get("max_attempts", body.get("max_attempts", 3)) or 3)
    retry_delay_minutes = int(body.get("retry_policy", {}).get("retry_delay_minutes", body.get("retry_delay_minutes", 30)) or 30)
    batch_size = int(body.get("throttle", body.get("batch_size", 250)) or 250)
    exclusion_id = body.get("exclusion_upload_id")
    exclude_predicate = body.get("exclude_predicate")

    try:
        candidates = portfolio.launch_candidates(
            portfolio_id=portfolio_id,
            exclusion_id=str(exclusion_id).strip() if exclusion_id else None,
            exclude_predicate=str(exclude_predicate).strip() if exclude_predicate else None,
        )
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)

    selected_rows = candidates["selected_rows"]
    customer_ids = [str(r.get("customer_id") or "").strip() for r in selected_rows if r.get("customer_id")]
    created = campaign_service.create_campaign(
        name=campaign_name,
        customer_ids=customer_ids,
        max_attempts=max_attempts,
        retry_delay_minutes=retry_delay_minutes,
        batch_size=batch_size,
    )
    campaign_id = str(created["campaign_id"])
    launch_config = {
        "retry_policy": body.get("retry_policy") or {"max_attempts": max_attempts, "retry_delay_minutes": retry_delay_minutes},
        "contact_window": body.get("contact_window") or {"start": "09:00", "end": "20:00"},
        "throttle": batch_size,
        "dpd_bucket_strategies": body.get("dpd_bucket_strategies") or {},
        "exclude_predicate": exclude_predicate,
        "exclusion_upload_id": exclusion_id,
        "excluded_count": candidates.get("excluded_count", 0),
    }
    launch_id = portfolio.record_launch(portfolio_id=portfolio_id, campaign_id=campaign_id, launch_config=launch_config, status="launched")
    tasks_created = workbench.seed_tasks(campaign_id=campaign_id, portfolio_id=portfolio_id, rows=selected_rows, actor=_actor(request))
    metrics = campaign_service.metrics(campaign_id)
    return {
        "ok": True,
        "campaign_id": campaign_id,
        "launch_id": launch_id,
        "seeded_accounts": len(customer_ids),
        "tasks_created": tasks_created,
        "excluded_count": candidates.get("excluded_count", 0),
        "metrics": metrics,
    }


@app.get("/api/portfolios")
async def api_portfolios(request: Request):
    deny = _require_role(request, ("ADMIN", "SUPERVISOR", "VIEWER"))
    if deny:
        return deny
    demo = _get_demo_singletons()
    portfolio: PortfolioService = demo["portfolio"]  # type: ignore[assignment]
    page, page_size = _pagination(request)
    out = portfolio.list_portfolios(limit=page_size, offset=(page - 1) * page_size)
    return {"rows": out["rows"], "total": out["total"], "page": page, "page_size": page_size}


@app.get("/api/portfolio/{portfolio_id}")
async def api_portfolio_get(portfolio_id: str, request: Request):
    deny = _require_role(request, ("ADMIN", "SUPERVISOR", "VIEWER"))
    if deny:
        return deny
    demo = _get_demo_singletons()
    portfolio: PortfolioService = demo["portfolio"]  # type: ignore[assignment]
    row = portfolio.get_portfolio(portfolio_id)
    if not row:
        return JSONResponse({"error": "portfolio_not_found"}, status_code=404)
    return row


@app.get("/api/sessions")
async def api_sessions(request: Request):
    deny = _require_role(request, ("ADMIN", "SUPERVISOR", "VIEWER"))
    if deny:
        return deny
    demo = _get_demo_singletons()
    sessions: Dict[str, dict] = demo["sessions"]  # type: ignore[assignment]
    campaign_id = (request.query_params.get("campaign_id") or "").strip()
    dpd_bucket = (request.query_params.get("bucket") or "").strip()
    disposition = (request.query_params.get("disposition") or "").strip()
    rows = list(sessions.values())
    if campaign_id:
        rows = [s for s in rows if str(s.get("campaign_id") or "") == campaign_id]
    if dpd_bucket:
        rows = [s for s in rows if str(s.get("dpd_bucket") or "") == dpd_bucket]
    if disposition:
        rows = [s for s in rows if str(s.get("disposition") or "") == disposition]
    # Return "active" snapshots (updated by the WS session loop).
    return {"sessions": rows}


@app.get("/api/tasks")
async def api_tasks(request: Request):
    deny = _require_role(request, ("ADMIN", "SUPERVISOR", "VIEWER"))
    if deny:
        return deny
    demo = _get_demo_singletons()
    workbench: WorkbenchService = demo["workbench"]  # type: ignore[assignment]
    page, page_size = _pagination(request)
    out = workbench.list_tasks(
        campaign_id=(request.query_params.get("campaign_id") or "").strip() or None,
        state=(request.query_params.get("state") or "").strip() or None,
        dpd_bucket=(request.query_params.get("dpd_bucket") or "").strip() or None,
        q=(request.query_params.get("q") or "").strip() or None,
        sort=(request.query_params.get("sort") or "updated_desc").strip(),
        page=page,
        page_size=page_size,
    )
    return out


@app.get("/api/tasks/summary")
async def api_tasks_summary(request: Request):
    deny = _require_role(request, ("ADMIN", "SUPERVISOR", "VIEWER"))
    if deny:
        return deny
    demo = _get_demo_singletons()
    workbench: WorkbenchService = demo["workbench"]  # type: ignore[assignment]
    campaign_id = (request.query_params.get("campaign_id") or "").strip() or None
    return workbench.summary_by_state(campaign_id=campaign_id)


@app.get("/api/tasks/{task_id}")
async def api_task_get(task_id: str, request: Request):
    deny = _require_role(request, ("ADMIN", "SUPERVISOR", "VIEWER"))
    if deny:
        return deny
    demo = _get_demo_singletons()
    workbench: WorkbenchService = demo["workbench"]  # type: ignore[assignment]
    task = workbench.get_task(task_id)
    if not task:
        return JSONResponse({"error": "task_not_found"}, status_code=404)
    return task


@app.post("/api/tasks/{task_id}/claim")
async def api_task_claim(task_id: str, request: Request):
    deny = _require_role(request, ("ADMIN", "SUPERVISOR"))
    if deny:
        return deny
    demo = _get_demo_singletons()
    workbench: WorkbenchService = demo["workbench"]  # type: ignore[assignment]
    result = workbench.claim_task(task_id=task_id, actor=_actor(request))
    status = 200 if result.get("ok") else 409
    return JSONResponse(result, status_code=status)


@app.post("/api/tasks/{task_id}/update")
async def api_task_update(task_id: str, request: Request):
    deny = _require_role(request, ("ADMIN", "SUPERVISOR"))
    if deny:
        return deny
    demo = _get_demo_singletons()
    workbench: WorkbenchService = demo["workbench"]  # type: ignore[assignment]
    try:
        body = await request.json()
    except Exception:
        body = {}
    result = workbench.update_task(
        task_id=task_id,
        actor=_actor(request),
        role=_get_role(request),
        state=body.get("state"),
        disposition=body.get("disposition"),
        notes=body.get("notes"),
        callback_at=body.get("callback_at"),
        compliance_override=bool(body.get("compliance_override", False)),
        escalate_reason=body.get("escalate_reason"),
    )
    status = 200 if result.get("ok") else 400
    return JSONResponse(result, status_code=status)


@app.post("/api/tasks/bulk_update")
async def api_tasks_bulk_update(request: Request):
    deny = _require_role(request, ("ADMIN", "SUPERVISOR"))
    if deny:
        return deny
    demo = _get_demo_singletons()
    workbench: WorkbenchService = demo["workbench"]  # type: ignore[assignment]
    try:
        body = await request.json()
    except Exception:
        body = {}
    ids = body.get("ids") if isinstance(body.get("ids"), list) else []
    action = str(body.get("action") or "").strip()
    payload = body.get("payload") if isinstance(body.get("payload"), dict) else {}
    result = workbench.bulk_update(ids=[str(i) for i in ids], actor=_actor(request), role=_get_role(request), action=action, payload=payload)
    return result


@app.get("/api/sessions/{session_id}/timeline")
async def api_session_timeline(session_id: str, request: Request):
    deny = _require_role(request, ("ADMIN", "SUPERVISOR", "VIEWER"))
    if deny:
        return deny
    demo = _get_demo_singletons()
    audit: SQLiteAuditStore = demo["audit"]  # type: ignore[assignment]
    session_objs: Dict[str, WebCallSession] = demo["session_objs"]  # type: ignore[assignment]
    timeline = audit.session_timeline(session_id)
    active = session_objs.get(session_id)
    if active:
        for ev in active.get_timeline():
            if isinstance(ev, dict):
                timeline.append(dict(ev))
        timeline.sort(key=lambda x: float(x.get("ts") or 0))
    return {"session_id": session_id, "timeline": timeline}


@app.get("/api/compliance/violations")
async def api_compliance_violations(request: Request):
    deny = _require_role(request, ("ADMIN", "SUPERVISOR", "VIEWER"))
    if deny:
        return deny
    demo = _get_demo_singletons()
    audit: SQLiteAuditStore = demo["audit"]  # type: ignore[assignment]
    severity = (request.query_params.get("severity") or "").strip() or None
    session_id = (request.query_params.get("session_id") or "").strip() or None
    return {"rows": audit.list_compliance_violations(severity=severity, session_id=session_id, limit=300)}


@app.get("/api/alerts")
async def api_alerts(request: Request):
    deny = _require_role(request, ("ADMIN", "SUPERVISOR", "VIEWER"))
    if deny:
        return deny
    demo = _get_demo_singletons()
    alerts: AlertsService = demo["alerts"]  # type: ignore[assignment]
    page, page_size = _pagination(request)
    return alerts.list_alerts(
        status=(request.query_params.get("status") or "").strip() or None,
        severity=(request.query_params.get("severity") or "").strip() or None,
        rtype=(request.query_params.get("type") or "").strip() or None,
        page=page,
        page_size=page_size,
    )


@app.get("/api/alerts/{alert_id}")
async def api_alert_get(alert_id: str, request: Request):
    deny = _require_role(request, ("ADMIN", "SUPERVISOR", "VIEWER"))
    if deny:
        return deny
    demo = _get_demo_singletons()
    alerts: AlertsService = demo["alerts"]  # type: ignore[assignment]
    row = alerts.get_alert(alert_id)
    if not row:
        return JSONResponse({"error": "alert_not_found"}, status_code=404)
    return row


@app.post("/api/alerts/{alert_id}/ack")
async def api_alert_ack(alert_id: str, request: Request):
    deny = _require_role(request, ("ADMIN", "SUPERVISOR"))
    if deny:
        return deny
    demo = _get_demo_singletons()
    alerts: AlertsService = demo["alerts"]  # type: ignore[assignment]
    ok = alerts.ack_alert(alert_id=alert_id, actor=_actor(request))
    return {"ok": ok}


@app.post("/api/alerts/{alert_id}/assign")
async def api_alert_assign(alert_id: str, request: Request):
    deny = _require_role(request, ("ADMIN", "SUPERVISOR"))
    if deny:
        return deny
    demo = _get_demo_singletons()
    alerts: AlertsService = demo["alerts"]  # type: ignore[assignment]
    try:
        body = await request.json()
    except Exception:
        body = {}
    assignee = str(body.get("assignee") or "").strip()
    if not assignee:
        return JSONResponse({"ok": False, "error": "assignee_required"}, status_code=400)
    ok = alerts.assign_alert(alert_id=alert_id, assignee=assignee, actor=_actor(request))
    return {"ok": ok}


@app.post("/api/alerts/{alert_id}/resolve")
async def api_alert_resolve(alert_id: str, request: Request):
    deny = _require_role(request, ("ADMIN", "SUPERVISOR"))
    if deny:
        return deny
    demo = _get_demo_singletons()
    alerts: AlertsService = demo["alerts"]  # type: ignore[assignment]
    ok = alerts.resolve_alert(alert_id=alert_id, actor=_actor(request))
    return {"ok": ok}


@app.get("/api/alert_rules")
async def api_alert_rules(request: Request):
    deny = _require_role(request, ("ADMIN", "SUPERVISOR", "VIEWER"))
    if deny:
        return deny
    demo = _get_demo_singletons()
    alerts: AlertsService = demo["alerts"]  # type: ignore[assignment]
    return {"rows": alerts.list_rules()}


@app.post("/api/alert_rules")
async def api_alert_rules_upsert(request: Request):
    deny = _require_role(request, ("ADMIN",))
    if deny:
        return deny
    demo = _get_demo_singletons()
    alerts: AlertsService = demo["alerts"]  # type: ignore[assignment]
    try:
        body = await request.json()
    except Exception:
        body = {}
    try:
        row = alerts.upsert_rule(
            rule_id=body.get("id"),
            name=str(body.get("name") or "Rule"),
            rtype=str(body.get("type") or ""),
            enabled=bool(body.get("enabled", True)),
            threshold=body.get("threshold_json") if isinstance(body.get("threshold_json"), dict) else {},
            routing=body.get("routing_json") if isinstance(body.get("routing_json"), dict) else {},
        )
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    return {"ok": True, "rule": row}


@app.post("/api/alert_rules/{rule_id}/toggle")
async def api_alert_rule_toggle(rule_id: str, request: Request):
    deny = _require_role(request, ("ADMIN",))
    if deny:
        return deny
    demo = _get_demo_singletons()
    alerts: AlertsService = demo["alerts"]  # type: ignore[assignment]
    try:
        body = await request.json()
    except Exception:
        body = {}
    ok = alerts.toggle_rule(rule_id=rule_id, enabled=bool(body.get("enabled", False)))
    return {"ok": ok}


@app.post("/api/alerts/evaluate")
async def api_alerts_evaluate(request: Request):
    deny = _require_role(request, ("ADMIN", "SUPERVISOR"))
    if deny:
        return deny
    demo = _get_demo_singletons()
    alerts: AlertsService = demo["alerts"]  # type: ignore[assignment]
    return {"ok": True, "result": alerts.evaluate()}


@app.post("/api/campaigns")
async def api_create_campaign(request: Request):
    deny = _require_role(request, ("ADMIN", "SUPERVISOR"))
    if deny:
        return deny
    demo = _get_demo_singletons()
    source: ExcelCustomerSource = demo["source"]  # type: ignore[assignment]
    campaign_service: CampaignService = demo["campaign_service"]  # type: ignore[assignment]
    workbench: WorkbenchService = demo["workbench"]  # type: ignore[assignment]
    try:
        body = await request.json()
    except Exception:
        body = {}
    name = (body.get("name") or f"Portfolio Campaign {int(time.time())}").strip()
    max_accounts = int(body.get("max_accounts") or 10000)
    max_attempts = int(body.get("max_attempts") or 3)
    retry_delay_minutes = int(body.get("retry_delay_minutes") or 30)
    batch_size = int(body.get("batch_size") or 250)
    rows = source.list_customers()
    selected_rows = rows[: max(1, max_accounts)]
    customer_ids = [str(r.get("customer_id") or "").strip() for r in selected_rows]
    created = campaign_service.create_campaign(
        name=name,
        customer_ids=customer_ids,
        max_attempts=max_attempts,
        retry_delay_minutes=retry_delay_minutes,
        batch_size=batch_size,
    )
    task_rows = [
        {
            "customer_id": r.get("customer_id"),
            "phone": r.get("phone"),
            "amount_due": r.get("overdue_amount"),
            "dpd": r.get("dpd"),
            "language": r.get("language_preference"),
            "customer_name": r.get("customer_name"),
        }
        for r in selected_rows
    ]
    tasks_created = workbench.seed_tasks(
        campaign_id=str(created["campaign_id"]),
        portfolio_id="legacy_source",
        rows=task_rows,
        actor=_actor(request),
    )
    return {"ok": True, **created, "tasks_created": tasks_created}


@app.post("/api/campaigns/{campaign_id}/start")
async def api_start_campaign(campaign_id: str, request: Request):
    deny = _require_role(request, ("ADMIN", "SUPERVISOR"))
    if deny:
        return deny
    demo = _get_demo_singletons()
    campaign_service: CampaignService = demo["campaign_service"]  # type: ignore[assignment]
    tasks: Dict[str, asyncio.Task] = demo["campaign_tasks"]  # type: ignore[assignment]
    campaign_service.set_status(campaign_id, "active")
    if campaign_id not in tasks or tasks[campaign_id].done():
        tasks[campaign_id] = asyncio.create_task(_campaign_run_loop(campaign_id), name=f"campaign_{campaign_id}")
    return {"ok": True, "campaign_id": campaign_id, "status": "active"}


@app.post("/api/campaigns/{campaign_id}/pause")
async def api_pause_campaign(campaign_id: str, request: Request):
    deny = _require_role(request, ("ADMIN", "SUPERVISOR"))
    if deny:
        return deny
    demo = _get_demo_singletons()
    campaign_service: CampaignService = demo["campaign_service"]  # type: ignore[assignment]
    tasks: Dict[str, asyncio.Task] = demo["campaign_tasks"]  # type: ignore[assignment]
    campaign_service.set_status(campaign_id, "paused")
    t = tasks.get(campaign_id)
    if t and not t.done():
        t.cancel()
    tasks.pop(campaign_id, None)
    return {"ok": True, "campaign_id": campaign_id, "status": "paused"}


@app.get("/api/campaigns/{campaign_id}/metrics")
async def api_campaign_metrics(campaign_id: str, request: Request):
    deny = _require_role(request, ("ADMIN", "SUPERVISOR", "VIEWER"))
    if deny:
        return deny
    demo = _get_demo_singletons()
    campaign_service: CampaignService = demo["campaign_service"]  # type: ignore[assignment]
    return campaign_service.metrics(campaign_id)


@app.get("/api/campaigns")
async def api_campaigns(request: Request):
    deny = _require_role(request, ("ADMIN", "SUPERVISOR", "VIEWER"))
    if deny:
        return deny
    demo = _get_demo_singletons()
    campaign_service: CampaignService = demo["campaign_service"]  # type: ignore[assignment]
    return {"rows": campaign_service.list_campaigns(limit=50)}


@app.get("/api/outbound/status")
async def api_outbound_status(request: Request):
    deny = _require_role(request, ("ADMIN", "SUPERVISOR", "VIEWER"))
    if deny:
        return deny
    demo = _get_demo_singletons()
    crm: CRMAdapter = demo["crm"]  # type: ignore[assignment]
    return crm.status()


@app.get("/api/reports")
async def api_reports(request: Request):
    deny = _require_role(request, ("ADMIN", "SUPERVISOR", "VIEWER"))
    if deny:
        return deny
    demo = _get_demo_singletons()
    reports: ReportsService = demo["reports"]  # type: ignore[assignment]
    page, page_size = _pagination(request)
    campaign_id = (request.query_params.get("campaign_id") or "").strip() or None
    out = reports.list_reports(page=page, page_size=page_size, campaign_id=campaign_id)
    out["schedule"] = reports.get_schedule()
    return out


@app.post("/api/reports/generate")
async def api_reports_generate(request: Request):
    deny = _require_role(request, ("ADMIN", "SUPERVISOR"))
    if deny:
        return deny
    demo = _get_demo_singletons()
    reports: ReportsService = demo["reports"]  # type: ignore[assignment]
    campaign_service: CampaignService = demo["campaign_service"]  # type: ignore[assignment]
    try:
        body = await request.json()
    except Exception:
        body = {}
    campaign_id = (body.get("campaign_id") or "").strip()
    report_date = (body.get("report_date") or "").strip() or None
    rows = []
    if campaign_id:
        rows = [campaign_id]
    else:
        rows = [str(r.get("campaign_id")) for r in campaign_service.list_campaigns(limit=500) if r.get("campaign_id")]
    created = []
    for cid in rows:
        with contextlib.suppress(Exception):
            created.append(reports.generate_report(campaign_id=cid, report_date=report_date))
    return {"ok": True, "count": len(created), "rows": created}


@app.post("/api/reports/schedule")
async def api_reports_schedule(request: Request):
    deny = _require_role(request, ("ADMIN",))
    if deny:
        return deny
    demo = _get_demo_singletons()
    reports: ReportsService = demo["reports"]  # type: ignore[assignment]
    try:
        body = await request.json()
    except Exception:
        body = {}
    enabled = bool(body.get("enabled", True))
    daily_time = str(body.get("daily_time") or "09:00")
    return {"ok": True, "schedule": reports.set_schedule(enabled=enabled, daily_time=daily_time)}


@app.get("/api/reports/{report_id}/download")
async def api_reports_download(report_id: str, request: Request):
    deny = _require_role(request, ("ADMIN", "SUPERVISOR", "VIEWER"))
    if deny:
        return deny
    demo = _get_demo_singletons()
    reports: ReportsService = demo["reports"]  # type: ignore[assignment]
    row = reports.get_report(report_id)
    if not row:
        return JSONResponse({"error": "report_not_found"}, status_code=404)
    fmt = (request.query_params.get("format") or "json").strip().lower()
    if fmt == "csv":
        return FileResponse(row["path_csv"], filename=f"{report_id}.csv")
    return FileResponse(row["path_json"], filename=f"{report_id}.json")


@app.post("/api/integrations/crm/replay/{session_id}")
async def api_crm_replay(session_id: str, request: Request):
    deny = _require_role(request, ("ADMIN", "SUPERVISOR"))
    if deny:
        return deny
    demo = _get_demo_singletons()
    crm: CRMAdapter = demo["crm"]  # type: ignore[assignment]
    return crm.replay_session(session_id)


@app.post("/api/integrations/crm/mock")
async def api_crm_mock(request: Request):
    deny = _require_role(request, ("ADMIN", "SUPERVISOR"))
    if deny:
        return deny
    demo = _get_demo_singletons()
    crm: CRMAdapter = demo["crm"]  # type: ignore[assignment]
    try:
        body = await request.json()
    except Exception:
        body = {}
    should_fail = bool(body.get("should_fail", False))
    payload = body.get("payload") if isinstance(body.get("payload"), dict) else body
    return crm.mock_receive(payload=payload, should_fail=should_fail)


@app.post("/api/integrations/lms/inbound")
async def api_lms_inbound(request: Request):
    pilot_mode = get_env_bool("PILOT_MODE", False)
    if not pilot_mode:
        return JSONResponse({"error": "pilot_mode_disabled"}, status_code=403)
    demo = _get_demo_singletons()
    sync: SyncService = demo["sync"]  # type: ignore[assignment]
    try:
        body = await request.json()
    except Exception:
        body = {}
    try:
        out = sync.inbound_lms(body, actor=_actor(request))
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    return out


@app.get("/api/integrations/sync_events")
async def api_sync_events(request: Request):
    deny = _require_role(request, ("ADMIN", "SUPERVISOR", "VIEWER"))
    if deny:
        return deny
    demo = _get_demo_singletons()
    sync: SyncService = demo["sync"]  # type: ignore[assignment]
    page, page_size = _pagination(request)
    return sync.list_sync_events(
        direction=(request.query_params.get("direction") or "").strip() or None,
        status=(request.query_params.get("status") or "").strip() or None,
        page=page,
        page_size=page_size,
    )


@app.get("/api/integrations/conflicts")
async def api_sync_conflicts(request: Request):
    deny = _require_role(request, ("ADMIN", "SUPERVISOR", "VIEWER"))
    if deny:
        return deny
    demo = _get_demo_singletons()
    sync: SyncService = demo["sync"]  # type: ignore[assignment]
    page, page_size = _pagination(request)
    return sync.list_conflicts(
        status=(request.query_params.get("status") or "").strip() or None,
        page=page,
        page_size=page_size,
    )


@app.post("/api/integrations/conflicts/{conflict_id}/resolve")
async def api_sync_conflict_resolve(conflict_id: str, request: Request):
    deny = _require_role(request, ("ADMIN", "SUPERVISOR"))
    if deny:
        return deny
    demo = _get_demo_singletons()
    sync: SyncService = demo["sync"]  # type: ignore[assignment]
    try:
        body = await request.json()
    except Exception:
        body = {}
    action = str(body.get("action") or "").strip().upper()
    try:
        out = sync.resolve_conflict(
            conflict_id=conflict_id,
            action=action,
            resolved_by=_actor(request),
            manual_override=body.get("manual_override") if isinstance(body.get("manual_override"), dict) else None,
        )
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    return out


@app.get("/api/integrations/dead_letters")
async def api_sync_dead_letters(request: Request):
    deny = _require_role(request, ("ADMIN", "SUPERVISOR", "VIEWER"))
    if deny:
        return deny
    demo = _get_demo_singletons()
    sync: SyncService = demo["sync"]  # type: ignore[assignment]
    page, page_size = _pagination(request)
    return sync.list_dead_letters(page=page, page_size=page_size)


@app.post("/api/integrations/dead_letters/{queue_id}/replay")
async def api_sync_dead_letter_replay(queue_id: str, request: Request):
    deny = _require_role(request, ("ADMIN", "SUPERVISOR"))
    if deny:
        return deny
    demo = _get_demo_singletons()
    sync: SyncService = demo["sync"]  # type: ignore[assignment]
    return sync.replay_dead_letter(queue_id, actor=_actor(request))


@app.post("/api/sessions/{session_id}/disposition")
async def api_set_disposition(session_id: str, request: Request):
    deny = _require_role(request, ("ADMIN", "SUPERVISOR"))
    if deny:
        return deny
    demo = _get_demo_singletons()
    objs: Dict[str, WebCallSession] = demo["session_objs"]  # type: ignore[assignment]
    sessions: Dict[str, dict] = demo["sessions"]  # type: ignore[assignment]
    sess = objs.get(session_id)
    if not sess:
        return JSONResponse({"error": "unknown session"}, status_code=404)
    try:
        data = await request.json()
    except Exception:
        data = {}
    disp = (data.get("disposition") or "").strip() or "closed"
    try:
        await sess.admin_set_disposition(disp)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    sessions[session_id] = sess.get_snapshot()
    return {"ok": True, "session": sessions[session_id]}


@app.get("/api/export/demo.xlsx")
async def api_export_demo(request: Request):
    deny = _require_role(request, ("ADMIN", "SUPERVISOR", "VIEWER"))
    if deny:
        return deny
    demo = _get_demo_singletons()
    sink: ExcelOutcomeSink = demo["sink"]  # type: ignore[assignment]
    audit: SQLiteAuditStore = demo["audit"]  # type: ignore[assignment]

    # Build a one-off export file with a Metrics sheet (client-friendly demo artifact).
    try:
        from openpyxl import load_workbook
    except Exception:
        return FileResponse(sink.path, filename="demo.xlsx")

    export_path = os.path.join(DATA_DIR, "demo_export.xlsx")
    wb = load_workbook(sink.path)
    try:
        if "Metrics" in wb.sheetnames:
            ws = wb["Metrics"]
            ws.delete_rows(1, ws.max_row)
        else:
            ws = wb.create_sheet("Metrics")
        m = audit.metrics()
        ws.append(["key", "value"])
        for k, v in m.items():
            ws.append([k, v])
        wb.save(export_path)
    finally:
        wb.close()

    return FileResponse(export_path, filename="demo.xlsx")


@app.post("/api/knowledge/reindex")
async def api_knowledge_reindex(request: Request):
    deny = _require_role(request, ("ADMIN", "SUPERVISOR"))
    if deny:
        return deny
    demo = _get_demo_singletons()
    knowledge: SQLiteFTSKnowledgeStore = demo["knowledge"]  # type: ignore[assignment]
    n = knowledge.reindex()
    return {"ok": True, "chunks_indexed": n}


class WebSocketSender:
    _CONTROL_MAX = 500
    _AUDIO_MAX = 300
    _CONTROL_BURST = 3

    def __init__(self, websocket: WebSocket) -> None:
        self.websocket = websocket
        self._control_queue: asyncio.Queue[str] = asyncio.Queue(maxsize=self._CONTROL_MAX)
        self._audio_queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=self._AUDIO_MAX)
        self._control_burst = 0
        self._task: Optional[asyncio.Task] = None
        self._closed = asyncio.Event()

    def start(self) -> None:
        if not self._task:
            self._task = asyncio.create_task(self._send_loop(), name="ws_send_loop")

    async def close(self) -> None:
        self._closed.set()
        if self._task and not self._task.done():
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task

    async def send_json(self, payload: dict) -> None:
        if self.websocket.application_state != WebSocketState.CONNECTED:
            return
        msg = json.dumps(payload)
        if self._control_queue.full():
            with contextlib.suppress(asyncio.QueueEmpty):
                _ = self._control_queue.get_nowait()
        with contextlib.suppress(asyncio.QueueFull):
            self._control_queue.put_nowait(msg)

    async def send_bytes(self, data: bytes) -> None:
        if self.websocket.application_state != WebSocketState.CONNECTED:
            return
        if self._audio_queue.full():
            with contextlib.suppress(asyncio.QueueEmpty):
                _ = self._audio_queue.get_nowait()
        with contextlib.suppress(asyncio.QueueFull):
            self._audio_queue.put_nowait(data)

    def _pick_ready_item(self) -> Optional[tuple[str, object]]:
        if self._control_burst < self._CONTROL_BURST:
            with contextlib.suppress(asyncio.QueueEmpty):
                self._control_burst += 1
                return ("text", self._control_queue.get_nowait())
        with contextlib.suppress(asyncio.QueueEmpty):
            self._control_burst = 0
            return ("bytes", self._audio_queue.get_nowait())
        with contextlib.suppress(asyncio.QueueEmpty):
            self._control_burst += 1
            return ("text", self._control_queue.get_nowait())
        with contextlib.suppress(asyncio.QueueEmpty):
            self._control_burst = 0
            return ("bytes", self._audio_queue.get_nowait())
        return None

    async def _send_loop(self) -> None:
        try:
            while not self._closed.is_set():
                if self.websocket.application_state != WebSocketState.CONNECTED:
                    break
                item = self._pick_ready_item()
                if item is None:
                    await asyncio.sleep(0.01)
                    continue
                kind, payload = item
                try:
                    if kind == "text":
                        await self.websocket.send_text(str(payload))
                    else:
                        await self.websocket.send_bytes(bytes(payload))
                except (RuntimeError, WebSocketDisconnect):
                    break
        finally:
            self._closed.set()


@app.websocket("/ws/voice")
async def voice_socket(websocket: WebSocket) -> None:
    await websocket.accept()
    sender = WebSocketSender(websocket)
    sender.start()
    demo = _get_demo_singletons()
    audit: SQLiteAuditStore = demo["audit"]  # type: ignore[assignment]
    sink: ExcelOutcomeSink = demo["sink"]  # type: ignore[assignment]
    source: ExcelCustomerSource = demo["source"]  # type: ignore[assignment]
    router: ActionRouter = demo["router"]  # type: ignore[assignment]
    knowledge: SQLiteFTSKnowledgeStore = demo["knowledge"]  # type: ignore[assignment]
    strategy: StrategyEngine = demo["strategy"]  # type: ignore[assignment]
    compliance: ComplianceEngine = demo["compliance"]  # type: ignore[assignment]
    followups: FollowupService = demo["followups"]  # type: ignore[assignment]
    crm: CRMAdapter = demo["crm"]  # type: ignore[assignment]
    sessions: Dict[str, dict] = demo["sessions"]  # type: ignore[assignment]
    session_objs: Dict[str, WebCallSession] = demo["session_objs"]  # type: ignore[assignment]

    client = websocket.client
    log_event(
        logger,
        "ws_open",
        client=f"{client.host}:{client.port}" if client else None,
    )

    def _extract_context_from_payload(data: dict) -> dict:
        # Accept either {type: 'context', context: {...}} OR flat keys on the payload.
        ctx = data.get("context") if isinstance(data.get("context"), dict) else {}
        if not isinstance(ctx, dict):
            ctx = {}

        # Merge flat keys (excluding type/context) if caller sends them at top-level.
        for k, v in (data or {}).items():
            if k in {"type", "context"}:
                continue
            if v is None:
                continue
            ctx.setdefault(k, v)

        # Normalize common aliases
        # amount / overdue
        if "overdue_amount" not in ctx:
            if "amount" in ctx:
                ctx["overdue_amount"] = ctx.get("amount")
            elif "overdue" in ctx:
                ctx["overdue_amount"] = ctx.get("overdue")

        # due date
        if "due_date" not in ctx:
            if "due" in ctx:
                ctx["due_date"] = ctx.get("due")
            elif "overdue_date" in ctx:
                ctx["due_date"] = ctx.get("overdue_date")

        # customer name
        if "customer_name" not in ctx and "name" in ctx:
            ctx["customer_name"] = ctx.get("name")

        # Normalize empty strings
        cleaned = {}
        for k, v in ctx.items():
            if isinstance(v, str):
                vv = v.strip()
                if vv:
                    cleaned[k] = vv
            else:
                cleaned[k] = v
        return cleaned

    load_dotenv(override=True)
    stt_ws_url = get_env(
        "SAARIKA_WS_URL",
        get_env("SARVAM_STT_WS_URL", "wss://api.sarvam.ai/speech-to-text/ws"),
    )
    llm_base_url = get_env("SARVAM_BASE_URL", "https://api.sarvam.ai")
    tts_ws_url = get_env(
        "BULBUL_WS_URL",
        get_env("SARVAM_TTS_WS_URL", "wss://api.sarvam.ai/text-to-speech/ws"),
    )

    api_key = get_env("SARVAM_API_KEY")
    stt_api_key = get_env("SAARIKA_API_KEY", api_key)
    llm_api_key = get_env("SARVAM_LLM_API_KEY", api_key)
    tts_api_key = get_env("BULBUL_API_KEY", api_key)
    if not stt_api_key:
        log_event(logger, "config_error", error="Missing SAARIKA_API_KEY for STT.")
        await sender.send_json({"type": "error", "message": "Missing SAARIKA_API_KEY for STT."})
        await websocket.close()
        return

    llm_model = get_env("SARVAM_CHAT_MODEL", get_env("SARVAM_LLM_MODEL", "sarvam-m"))
    tts_voice = get_env("BULBUL_VOICE")
    tts_speaker = get_env("SARVAM_TTS_SPEAKER")
    stt_model = get_env("SARVAM_STT_MODEL")
    tts_model = get_env("SARVAM_TTS_MODEL")
    stt_language = get_env("SARVAM_STT_LANGUAGE", "en-IN")
    stt_language_key = get_env("SARVAM_STT_LANGUAGE_PARAM", "language_code")

    vad_threshold = float(get_env("VAD_RMS_THRESHOLD", "500"))
    vad_silence_ms = int(get_env("VAD_SILENCE_MS", "600"))
    stt_flush_interval_ms = int(get_env("STT_FLUSH_INTERVAL_MS", "250"))
    stt_vad_signals = get_env_bool("STT_VAD_SIGNALS", True)
    stt_high_vad = get_env_bool("STT_HIGH_VAD_SENSITIVITY", True)
    use_sdk = get_env_bool("USE_SARVAMAI_SDK", True)
    use_sdk_stt = get_env_bool("USE_SARVAMAI_SDK_STT", use_sdk)
    # SDK TTS streams MP3; browser/player expects PCM16. Default to raw WS unless explicitly enabled.
    use_sdk_tts = get_env_bool("USE_SARVAMAI_SDK_TTS", False)
    # LLM streaming via SDK doesn't handle event-stream correctly; default to HTTP SSE unless overridden.
    use_sdk_llm = get_env_bool("USE_SARVAMAI_SDK_LLM", False)
    stt_flush_signal_env = get_env("STT_FLUSH_SIGNAL")
    if stt_flush_signal_env is None or stt_flush_signal_env == "":
        stt_flush_signal = use_sdk_stt
    else:
        stt_flush_signal = get_env_bool("STT_FLUSH_SIGNAL", False)
    stt_audio_payload_format = get_env("STT_AUDIO_PAYLOAD_FORMAT", "flat")
    stt_input_audio_codec = get_env("STT_INPUT_AUDIO_CODEC", "pcm_s16le")
    stt_audio_encoding = get_env("STT_AUDIO_ENCODING")
    stt_log_raw = get_env_bool("LOG_STT_RAW", False)
    log_partials = get_env_bool("LOG_PARTIAL_TRANSCRIPTS", True)
    log_tokens = get_env_bool("LOG_LLM_TOKENS", False)
    log_audio_chunks = get_env_bool("LOG_TTS_CHUNKS", False)
    greeting_text = get_env(
        "GREETING_TEXT",
        "Hello, this is TuringEdge collections calling about your overdue payment. Is now a good time to talk?",
    )
    enable_greeting = get_env_bool("ENABLE_GREETING", True)
    max_history_turns = int(get_env("MAX_HISTORY_TURNS", "10"))
    session_store_path = get_env("SESSION_STORE_PATH")
    dynamic_stt_language = get_env_bool("STT_DYNAMIC_LANGUAGE", True)
    preview_partials = get_env_bool("PREVIEW_PARTIALS", True)
    preview_after_ms = int(get_env("PREVIEW_AFTER_MS", "300"))
    llm_timeout_s = float(get_env("LLM_STREAM_TIMEOUT_S", "20"))
    tts_timeout_s = float(get_env("TTS_STREAM_TIMEOUT_S", "20"))
    stt_connect_timeout_s = float(get_env("STT_CONNECT_TIMEOUT_S", "10"))
    tts_stream_chunk_chars = int(get_env("TTS_STREAM_CHUNK_CHARS", "30"))
    tts_stream_flush_punct = get_env_bool("TTS_STREAM_FLUSH_PUNCT", True)
    tts_min_buffer_size = int(get_env("TTS_MIN_BUFFER_SIZE", "30"))
    tts_max_chunk_length = int(get_env("TTS_MAX_CHUNK_LENGTH", "120"))
    tts_output_audio_codec = get_env("TTS_OUTPUT_AUDIO_CODEC", "linear16")
    tts_output_audio_bitrate = get_env("TTS_OUTPUT_AUDIO_BITRATE")
    post_speech_pause_ms = int(get_env("POST_SPEECH_PAUSE_MS", "600"))  # Default 600ms for human-like turns

    stt = SaarikaSTTService(
        ws_url=stt_ws_url,
        api_key=stt_api_key,
        model=stt_model,
        language=stt_language,
        language_param_key=stt_language_key,
        vad_signals=stt_vad_signals,
        high_vad_sensitivity=stt_high_vad,
        flush_signal=stt_flush_signal,
        audio_payload_format=stt_audio_payload_format,
        input_audio_codec=stt_input_audio_codec,
        audio_encoding=stt_audio_encoding,
        log_raw_messages=stt_log_raw,
        use_sdk=use_sdk_stt,
    )
    llm = SarvamLLMService(base_url=llm_base_url, api_key=llm_api_key, model=llm_model, use_sdk=use_sdk_llm)

    log_event(
        logger,
        "config_loaded",
        stt_ws_url=stt_ws_url,
        llm_base_url=llm_base_url,
        tts_ws_url=tts_ws_url,
        stt_model=stt_model,
        llm_model=llm_model,
        tts_model=tts_model,
        api_key_prefix=mask_secret(api_key),
        stt_key_prefix=mask_secret(stt_api_key),
        llm_key_prefix=mask_secret(llm_api_key),
        tts_key_prefix=mask_secret(tts_api_key),
        use_sdk=use_sdk,
        use_sdk_stt=use_sdk_stt,
        use_sdk_llm=use_sdk_llm,
        use_sdk_tts=use_sdk_tts,
        tts_output_audio_codec=tts_output_audio_codec,
        tts_min_buffer_size=tts_min_buffer_size,
        tts_max_chunk_length=tts_max_chunk_length,
    )

    session = WebCallSession(
        stt_service=stt,
        llm_service=llm,
        tts_ws_url=tts_ws_url,
        send_event=sender.send_json,
        send_audio=sender.send_bytes,
        tts_api_key=tts_api_key,
        tts_voice=tts_voice,
        tts_model=tts_model,
        tts_speaker=tts_speaker,
        greeting_text=greeting_text if enable_greeting else None,
        max_history_turns=max_history_turns,
        session_store_path=session_store_path,
        dynamic_stt_language=dynamic_stt_language,
        preview_partials=preview_partials,
        preview_after_ms=preview_after_ms,
        llm_timeout_s=llm_timeout_s,
        tts_timeout_s=tts_timeout_s,
        stt_connect_timeout_s=stt_connect_timeout_s,
        vad_rms_threshold=vad_threshold,
        vad_silence_ms=vad_silence_ms,
        stt_flush_interval_ms=stt_flush_interval_ms,
        log_partial_transcripts=log_partials,
        log_tokens=log_tokens,
        log_audio_chunks=log_audio_chunks,
        use_sdk=use_sdk_tts,
        tts_stream_chunk_chars=tts_stream_chunk_chars,
        tts_stream_flush_punct=tts_stream_flush_punct,
        tts_min_buffer_size=tts_min_buffer_size,
        tts_max_chunk_length=tts_max_chunk_length,
        tts_output_audio_codec=tts_output_audio_codec,
        tts_output_audio_bitrate=tts_output_audio_bitrate,
        post_speech_pause_ms=post_speech_pause_ms,
        audit_store=audit,
        excel_sink=sink,
        action_router=router,
        knowledge_store=knowledge,
        session_registry=sessions,
        strategy_engine=strategy,
        compliance_engine=compliance,
        followup_service=followups,
        crm_adapter=crm,
    )
    audit.record_event(event_type="ws_open", session_id=session._session_id, payload={"client": f"{client.host}:{client.port}" if client else None})
    sink.upsert_call(session_id=session._session_id, customer_id=None, start_ts=round(time.time(), 3))
    snap = session.get_snapshot()
    audit.upsert_outcome(
        session_id=session._session_id,
        start_ts=round(time.time(), 3),
        customer_id=snap.get("customer_id"),
        campaign_id=snap.get("campaign_id"),
        dpd_bucket=snap.get("dpd_bucket"),
    )
    sessions[session._session_id] = session.get_snapshot()
    session_objs[session._session_id] = session

    try:
        await session.start()
    except Exception as exc:
        log_event(logger, "session_start_failed", error=str(exc))
        await sender.send_json({"type": "error", "message": "STT connection failed"})
        await websocket.close()
        return

    session_started = False
    try:
        while True:
            message = await websocket.receive()
            if message.get("type") == "websocket.disconnect":
                break
            if message.get("bytes") is not None:
                if not session_started:
                    continue
                await session.handle_audio(message["bytes"])
                continue
            if message.get("text"):
                try:
                    data = json.loads(message["text"])
                except json.JSONDecodeError:
                    continue
                msg_type = data.get("type")

                if msg_type == "start":
                    if session_started:
                        await sender.send_json({"type": "started"})
                        continue
                    # UI may send session context together with start.
                    ctx = _extract_context_from_payload(data)
                    if not ctx.get("customer_id"):
                        await sender.send_json({"type": "error", "message": "Please select a customer before starting."})
                        continue
                    if ctx and hasattr(session, "set_context"):
                        await session.set_context(ctx)
                    await sender.send_json({"type": "context_received", "context": ctx})
                    await sender.send_json({"type": "started"})
                    if hasattr(session, "start_greeting"):
                        await session.start_greeting()
                    sessions[session._session_id] = session.get_snapshot()
                    session_started = True
                    continue

                if msg_type == "stop":
                    break

                if msg_type == "ping":
                    await sender.send_json({"type": "pong"})
                    continue

                if msg_type == "audio_started":
                    if not session_started:
                        continue
                    log_event(logger, "audio_started", session_id=session._session_id)
                    audit.record_event(event_type="audio_started", session_id=session._session_id, payload={})
                    continue

                # Allow typed/text input from the UI (e.g., the yellow input block)
                if msg_type in {"text", "user_text", "chat"}:
                    if not session_started:
                        await sender.send_json({"type": "error", "message": "Start the session before sending text."})
                        continue
                    text = (data.get("text") or "").strip()
                    if text:
                        if hasattr(session, "handle_text"):
                            await session.handle_text(text)
                        else:
                            await sender.send_json(
                                {"type": "error", "message": "Text input is not supported by this server build."}
                            )
                        sessions[session._session_id] = session.get_snapshot()
                    continue

                # Allow the UI to pass known context (customer name / amount / due date etc.)
                if msg_type in {"set_context", "context"}:
                    ctx = _extract_context_from_payload(data)
                    if ctx and hasattr(session, "set_context"):
                        await session.set_context(ctx)
                    await sender.send_json({"type": "context_received", "context": ctx})
                    sessions[session._session_id] = session.get_snapshot()
                    continue


                if msg_type == "set_disposition":
                    disp = str(data.get("disposition") or "").strip()
                    if disp and hasattr(session, "_wf_state"):
                        session._wf_state.disposition = disp
                        log_event(logger, "manual_disposition", session_id=session._session_id, disposition=disp)
                        await sender.send_json({"type": "disposition_set", "disposition": disp})
                        sessions[session._session_id] = session.get_snapshot()
                    continue

                if msg_type == "action":
                    if not session_started:
                        await sender.send_json(
                            {"type": "action_error", "name": data.get("name"), "ok": False, "error": "Start the session before taking actions."}
                        )
                        continue
                    name = str(data.get("name") or "").strip()
                    payload = data.get("payload")
                    if not isinstance(payload, dict):
                        payload = {}
                    if not name:
                        await sender.send_json(
                            {"type": "action_error", "name": name, "ok": False, "error": "Missing action name."}
                        )
                        continue
                    try:
                        result = await session.handle_action(name=name, payload=payload)
                    except Exception as exc:
                        await sender.send_json(
                            {"type": "action_error", "name": name, "ok": False, "error": str(exc)}
                        )
                        continue
                    await sender.send_json({"type": "action_result", "name": name, "ok": True, "result": result})
                    sessions[session._session_id] = session.get_snapshot()
                    continue
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.exception("Websocket error: %s", exc)
    finally:
        # Final snapshot + outcome.
        try:
            sessions[session._session_id] = session.get_snapshot()
        except Exception as exc:
            log_event(logger, "session_snapshot_error", session_id=session._session_id, error=str(exc))
        await session.stop()
        await sender.close()
        try:
            session_objs.pop(session._session_id, None)
        except Exception as exc:
            log_event(logger, "session_registry_remove_error", session_id=session._session_id, error=str(exc))
        try:
            audit.upsert_outcome(
                session_id=session._session_id,
                end_ts=round(time.time(), 3),
                customer_id=session.get_snapshot().get("customer_id"),
                campaign_id=session.get_snapshot().get("campaign_id"),
                dpd_bucket=session.get_snapshot().get("dpd_bucket"),
                disposition=session.get_snapshot().get("disposition"),
                ptp_date=session.get_snapshot().get("ptp_date"),
                callback_time=session.get_snapshot().get("callback_time"),
            )
            sink.upsert_call(
                session_id=session._session_id,
                customer_id=session.get_snapshot().get("customer_id"),
                end_ts=round(time.time(), 3),
                disposition=session.get_snapshot().get("disposition"),
                ptp_date=session.get_snapshot().get("ptp_date"),
                callback_time=session.get_snapshot().get("callback_time"),
            )
        except Exception as exc:
            log_event(logger, "session_finalize_persist_error", session_id=session._session_id, error=str(exc))
        log_event(logger, "ws_close")


def main() -> None:
    import uvicorn

    load_dotenv(override=True)
    configure_logging()
    host = get_env("API_HOST", "0.0.0.0")
    port = int(get_env("API_PORT", get_env("PORT", "8000")))
    log_level = get_env("LOG_LEVEL", "info").lower()

    uvicorn.run("web_app:app", host=host, port=port, log_level=log_level, reload=False)


if __name__ == "__main__":
    configure_logging()
    main()
