.PHONY: dev test build

dev:
	@/bin/bash -c 'set -e; \
	DEMO_MODE=1 PILOT_MODE=1 JWT_SECRET=dev-jwt-secret python3 -m uvicorn web_app:app --reload --host 127.0.0.1 --port 8000 & \
	BACK_PID=$$!; \
	cd frontend-react && npm run dev & \
	FRONT_PID=$$!; \
	trap "kill $$BACK_PID $$FRONT_PID" INT TERM EXIT; \
	wait'

test:
	pytest -q

build:
	cd frontend-react && npm run build
