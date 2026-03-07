import {
  Badge,
  Button,
  Card,
  Checkbox,
  Divider,
  Drawer,
  Group,
  Loader,
  ScrollArea,
  Select,
  SimpleGrid,
  Stack,
  Switch,
  Table,
  Text,
  TextInput,
  Title,
} from "@mantine/core";
import dayjs from "dayjs";
import { notifications } from "@mantine/notifications";
import { useEffect, useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowRightLeft, ClipboardCheck, RefreshCcw, ShieldAlert } from "lucide-react";

import { apiFetch, toQuery } from "../../api/client";
import { useAuth } from "../../auth/AuthProvider";
import { PERMS, ROLES } from "../../auth/roles";
import { FlowGuide } from "../../components/FlowGuide";
import { ModuleHeader } from "../../components/ModuleHeader";
import { EmptyStateCard } from "../../components/EmptyStateCard";
import { SlaBadge } from "../../components/SlaBadge";
import type { SessionSnapshot, TaskDetail, TaskRow } from "../../types/api";

const STATES = ["NEW", "IN_PROGRESS", "PTP", "CALLBACK", "ESCALATED", "CLOSED"] as const;

function parseCompliance(jsonText?: string): Record<string, boolean> {
  try {
    const out = jsonText ? JSON.parse(jsonText) : {};
    if (out && typeof out === "object") {
      return out as Record<string, boolean>;
    }
  } catch {
    // ignore
  }
  return {
    CONSENT_OK: true,
    IDENTITY_OK: true,
    NO_THREATS_OK: true,
    SENSITIVE_ASKS_OK: true,
  };
}

export function WorkbenchPage() {
  const qc = useQueryClient();
  const { user, role, hasPermission } = useAuth();
  const canMutate = hasPermission(PERMS.WORKBENCH_MUTATE);
  const canOverride = [ROLES.ADMIN, ROLES.COLLECTIONS_MANAGER].includes((role || "").toUpperCase() as typeof ROLES.ADMIN);

  const [campaignId, setCampaignId] = useState("");
  const [stateFilter, setStateFilter] = useState("");
  const [dpdBucket, setDpdBucket] = useState("");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null);
  const [nextState, setNextState] = useState<string>("IN_PROGRESS");
  const [disposition, setDisposition] = useState("");
  const [notes, setNotes] = useState("");
  const [override, setOverride] = useState(false);
  const [assignee, setAssignee] = useState("");
  const [autoRefresh, setAutoRefresh] = useState(false);

  const tasksQuery = useQuery({
    queryKey: ["tasks", campaignId, stateFilter, dpdBucket, search, page, role, user?.username],
    queryFn: () =>
      apiFetch<{ rows: TaskRow[]; total: number; page: number; page_size: number }>(
        `/api/tasks${
          toQuery({
            campaign_id: campaignId,
            state: stateFilter,
            dpd_bucket: dpdBucket,
            q: search,
            sort: "updated_desc",
            page,
            page_size: 60,
          })
        }`
      ),
    refetchInterval: autoRefresh ? 10_000 : false,
  });

  const taskDetail = useQuery({
    queryKey: ["task_detail", selectedTaskId],
    queryFn: () => apiFetch<TaskDetail>(`/api/tasks/${encodeURIComponent(selectedTaskId || "")}`),
    enabled: !!selectedTaskId,
  });

  const sessionsQuery = useQuery({
    queryKey: ["sessions_lookup", selectedTaskId],
    queryFn: () => apiFetch<{ sessions: SessionSnapshot[] }>("/api/sessions"),
    enabled: !!selectedTaskId,
  });

  useEffect(() => {
    if (!taskDetail.data) return;
    setNextState(taskDetail.data.state || "IN_PROGRESS");
    setDisposition(taskDetail.data.disposition || "");
    setNotes(taskDetail.data.notes || "");
    setOverride(false);
  }, [taskDetail.data]);

  const visibleRows = useMemo(() => {
    const rows = tasksQuery.data?.rows || [];
    if ((role || "").toUpperCase() === ROLES.CALLING_AGENT) {
      return rows.filter((r) => String(r.owner || "") === String(user?.username || ""));
    }
    return rows;
  }, [tasksQuery.data, role, user?.username]);

  const grouped = useMemo(() => {
    const out: Record<string, TaskRow[]> = {};
    STATES.forEach((s) => {
      out[s] = [];
    });
    visibleRows.forEach((r) => {
      out[r.state] = [...(out[r.state] || []), r];
    });
    return out;
  }, [visibleRows]);

  const refreshAll = async () => {
    await qc.invalidateQueries({ queryKey: ["tasks"] });
    if (selectedTaskId) {
      await qc.invalidateQueries({ queryKey: ["task_detail", selectedTaskId] });
    }
  };

  const claimTask = async (taskId: string) => {
    try {
      await apiFetch(`/api/tasks/${encodeURIComponent(taskId)}/claim`, { method: "POST" });
      notifications.show({ color: "green", message: "Task claimed" });
      await refreshAll();
    } catch (err) {
      notifications.show({ color: "red", message: String(err) });
    }
  };

  const saveUpdate = async () => {
    if (!selectedTaskId) return;
    try {
      await apiFetch(`/api/tasks/${encodeURIComponent(selectedTaskId)}/update`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          state: nextState,
          disposition,
          notes,
          compliance_override: override,
          escalate_reason: nextState === "ESCALATED" ? disposition || "manual_escalation" : undefined,
        }),
      });
      notifications.show({ color: "green", message: "Task updated" });
      await refreshAll();
    } catch (err) {
      notifications.show({ color: "red", message: String(err) });
    }
  };

  const bulkAction = async (action: "assign" | "close" | "escalate") => {
    if (!selectedIds.length) return;
    const payload =
      action === "assign"
        ? { owner: assignee || user?.username || "agent" }
        : action === "close"
          ? { disposition: "closed", notes: "bulk_close" }
          : { disposition: "escalated", reason: "bulk_escalation", notes: "bulk_escalation" };
    try {
      await apiFetch("/api/tasks/bulk_update", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ids: selectedIds, action, payload }),
      });
      notifications.show({ color: "green", message: `Bulk ${action} complete` });
      setSelectedIds([]);
      await refreshAll();
    } catch (err) {
      notifications.show({ color: "red", message: String(err) });
    }
  };

  const selectedSession = useMemo(() => {
    const detail = taskDetail.data;
    if (!detail) return null;
    return (sessionsQuery.data?.sessions || []).find((s) => String(s.customer_id || "") === String(detail.customer_id || "")) || null;
  }, [sessionsQuery.data, taskDetail.data]);

  if (tasksQuery.isLoading) {
    return (
      <Group justify="center" py="xl">
        <Loader />
      </Group>
    );
  }

  return (
    <Stack gap="md">
      <ModuleHeader
        title="Supervisor Workbench"
        subtitle="Operate queues, handle exceptions, and close outcomes with audit-safe actions"
        action={
          <Group>
            <Switch
              checked={autoRefresh}
              onChange={(e) => setAutoRefresh(e.currentTarget.checked)}
              label="Auto refresh (10s)"
            />
            <Button variant="light" leftSection={<RefreshCcw size={14} />} onClick={refreshAll}>
              Refresh
            </Button>
          </Group>
        }
      />

      <FlowGuide
        title="Workbench Flow"
        steps={[
          { title: "Filter Queue", detail: "Narrow by campaign, state, or DPD bucket" },
          { title: "Open Task", detail: "Click card to inspect full timeline + compliance" },
          { title: "Take Action", detail: "Update state/disposition or bulk action" },
          { title: "Close / Escalate", detail: "Finish case with immutable task event" },
        ]}
      />

      <Card className="te-section-card">
        <SimpleGrid cols={{ base: 1, md: 5 }}>
          <TextInput label="Campaign" placeholder="cmp-..." value={campaignId} onChange={(e) => setCampaignId(e.currentTarget.value)} />
          <Select label="State" value={stateFilter} onChange={(v) => setStateFilter(v || "")} data={[{ value: "", label: "All" }, ...STATES.map((s) => ({ value: s, label: s }))]} />
          <Select
            label="DPD Bucket"
            value={dpdBucket}
            onChange={(v) => setDpdBucket(v || "")}
            data={["", "1-30", "31-60", "61-90", "90+"].map((v) => ({ value: v, label: v || "All" }))}
          />
          <TextInput label="Search" placeholder="customer id or name" value={search} onChange={(e) => setSearch(e.currentTarget.value)} />
          <Group align="flex-end" gap="xs">
            <Button mt={24} onClick={() => setPage(1)} variant="light">
              Apply
            </Button>
          </Group>
        </SimpleGrid>
      </Card>

      {canMutate ? (
        <Card className="te-section-card te-data-card">
          <Group justify="space-between" align="end">
            <Group>
              <Text size="sm">Selected: {selectedIds.length}</Text>
              <TextInput size="xs" placeholder="assign to" value={assignee} onChange={(e) => setAssignee(e.currentTarget.value)} />
            </Group>
            <Group>
              <Button size="xs" variant="light" onClick={() => bulkAction("assign")} disabled={!selectedIds.length}>
                Bulk Assign
              </Button>
              <Button size="xs" variant="light" onClick={() => bulkAction("close")} disabled={!selectedIds.length}>
                Bulk Close
              </Button>
              <Button size="xs" color="orange" onClick={() => bulkAction("escalate")} disabled={!selectedIds.length}>
                Bulk Escalate
              </Button>
            </Group>
          </Group>
        </Card>
      ) : null}

      {!visibleRows.length ? (
        <EmptyStateCard
          title="No tasks in this queue"
          description="Adjust campaign, state, or DPD filters, or seed a new campaign from Portfolio to populate the supervisor board."
        />
      ) : (
        <ScrollArea offsetScrollbars className="te-subtle-scroll">
        <SimpleGrid cols={{ base: 1, md: 2, lg: 3, xl: 6 }}>
          {STATES.map((state) => (
            <Card key={state} className="te-data-card" style={{ minHeight: 440 }}>
              <Group justify="space-between" mb="sm">
                <Title order={4}>{state}</Title>
                <Badge variant="outline">{(grouped[state] || []).length}</Badge>
              </Group>
              <Stack gap="xs">
                {(grouped[state] || []).length === 0 ? (
                  <Text size="sm" c="dimmed">
                    No accounts in this state.
                  </Text>
                ) : null}
                {(grouped[state] || []).map((row) => (
                  <Card
                    key={row.id}
                    withBorder
                    style={{ cursor: "pointer", borderColor: row.compliance_block ? "#f59f00" : undefined }}
                    onClick={() => setSelectedTaskId(row.id)}
                  >
                    <Stack gap={4}>
                      <Group justify="space-between" wrap="nowrap">
                        <Text fw={700}>{row.customer_id}</Text>
                        {canMutate ? (
                          <Checkbox
                            checked={selectedIds.includes(row.id)}
                            onChange={(ev) => {
                              ev.stopPropagation();
                              const checked = ev.currentTarget.checked;
                              setSelectedIds((prev) => (checked ? [...prev, row.id] : prev.filter((id) => id !== row.id)));
                            }}
                          />
                        ) : null}
                      </Group>
                      <Text size="xs" c="dimmed">{row.customer_name || "Unnamed"}</Text>
                      <Text size="xs">Amount: {Number(row.amount_due || 0).toFixed(2)}</Text>
                      <Text size="xs">DPD: {row.dpd ?? "-"}</Text>
                      <Text size="xs">Owner: {row.owner || "Unassigned"}</Text>
                      <Text size="xs">Last: {row.last_action_at ? dayjs.unix(row.last_action_at).format("DD MMM HH:mm") : "-"}</Text>
                      <Group gap={6} wrap="wrap">
                        <SlaBadge breach={row.sla_breach} />
                        {row.compliance_block ? (
                          <Badge color="orange" variant="light" leftSection={<ShieldAlert size={12} />}>
                            Compliance Block
                          </Badge>
                        ) : null}
                      </Group>
                    </Stack>
                  </Card>
                ))}
              </Stack>
            </Card>
          ))}
        </SimpleGrid>
        </ScrollArea>
      )}

      <Drawer opened={!!selectedTaskId} onClose={() => setSelectedTaskId(null)} position="right" size="xl" title="Task Detail">
        {taskDetail.data ? (
          <Stack>
            <Group justify="space-between">
              <Stack gap={0}>
                <Title order={4}>{taskDetail.data.customer_id}</Title>
                <Text size="sm" c="dimmed">campaign {taskDetail.data.campaign_id}</Text>
              </Stack>
              <Group>
                <SlaBadge breach={taskDetail.data.sla_breach} />
                {taskDetail.data.compliance_block ? <Badge color="orange">Blocked</Badge> : null}
              </Group>
            </Group>

            <Card>
              <Group justify="space-between">
                <Stack gap={0}>
                  <Text size="sm">Transcript</Text>
                  {selectedSession?.session_id ? (
                    <a href={`/api/sessions/${encodeURIComponent(selectedSession.session_id)}/timeline`} target="_blank" rel="noreferrer">
                      Open conversation timeline
                    </a>
                  ) : (
                    <Text size="sm" c="dimmed">No linked session yet</Text>
                  )}
                </Stack>
                {canMutate ? (
                  <Button variant="light" leftSection={<ClipboardCheck size={14} />} onClick={() => claimTask(taskDetail.data!.id)}>
                    Claim
                  </Button>
                ) : null}
              </Group>
            </Card>

            <Card>
              <Text fw={600} mb="xs">Compliance Status</Text>
              <Group gap="xs" wrap="wrap">
                {Object.entries(parseCompliance(taskDetail.data.compliance_status_json)).map(([k, v]) => (
                  <Badge key={k} color={v ? "green" : "red"} variant="light">
                    {k}
                  </Badge>
                ))}
              </Group>
            </Card>

            <Card>
              <Title order={5} mb="sm">Actions</Title>
              <SimpleGrid cols={{ base: 1, md: 2 }}>
                <Select label="State" value={nextState} onChange={(v) => setNextState(v || "IN_PROGRESS")} data={STATES as unknown as string[]} />
                <TextInput label="Disposition" value={disposition} onChange={(e) => setDisposition(e.currentTarget.value)} />
              </SimpleGrid>
              <TextInput mt="sm" label="Notes" value={notes} onChange={(e) => setNotes(e.currentTarget.value)} />
              {canOverride ? <Checkbox mt="sm" checked={override} onChange={(e) => setOverride(e.currentTarget.checked)} label="Compliance override" /> : null}
              {canMutate ? (
                <Group justify="flex-end" mt="sm">
                  <Button onClick={saveUpdate} leftSection={<ArrowRightLeft size={14} />}>
                    Save Update
                  </Button>
                </Group>
              ) : null}
            </Card>

            <Card className="te-data-card">
              <Title order={5} mb="sm">Timeline</Title>
              <ScrollArea className="te-table-wrap te-subtle-scroll" offsetScrollbars>
                <Table>
                  <Table.Thead>
                    <Table.Tr>
                      <Table.Th>Time</Table.Th>
                      <Table.Th>Event</Table.Th>
                      <Table.Th>Actor</Table.Th>
                    </Table.Tr>
                  </Table.Thead>
                  <Table.Tbody>
                    {(taskDetail.data.events || []).map((ev) => (
                      <Table.Tr key={ev.id}>
                        <Table.Td>{dayjs.unix(ev.ts).format("DD MMM HH:mm:ss")}</Table.Td>
                        <Table.Td>{ev.event_type}</Table.Td>
                        <Table.Td>{ev.actor || "-"}</Table.Td>
                      </Table.Tr>
                    ))}
                  </Table.Tbody>
                </Table>
              </ScrollArea>
              <Divider my="sm" />
              <Text size="xs" c="dimmed">Immutable task events are recorded for every state transition.</Text>
            </Card>
          </Stack>
        ) : (
          <Text c="dimmed">Select a task card to inspect details.</Text>
        )}
      </Drawer>
    </Stack>
  );
}
