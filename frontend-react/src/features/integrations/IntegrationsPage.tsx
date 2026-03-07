import {
  Badge,
  Button,
  Card,
  Group,
  JsonInput,
  Modal,
  ScrollArea,
  Stack,
  Table,
  Tabs,
  Text,
  Title,
} from "@mantine/core";
import dayjs from "dayjs";
import { notifications } from "@mantine/notifications";
import { useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { apiFetch } from "../../api/client";
import { useAuth } from "../../auth/AuthProvider";
import { PERMS } from "../../auth/roles";
import { FlowGuide } from "../../components/FlowGuide";
import { ModuleHeader } from "../../components/ModuleHeader";
import { EmptyStateCard } from "../../components/EmptyStateCard";
import type { BuildInfo } from "../../types/api";

interface SyncEvent {
  id: string;
  ts: number;
  direction: string;
  status: string;
  entity_type: string;
  entity_id: string;
  attempts: number;
  last_error?: string;
  payload_json?: string;
}

interface ConflictRow {
  id: string;
  ts: number;
  entity_type: string;
  entity_id: string;
  status: string;
  field_diffs_json: string;
}

interface DeadLetterRow {
  queue_id: string;
  session_id: string;
  event_type: string;
  state: string;
  attempts: number;
  updated_ts: number;
}

function parseDiffs(raw: string): Array<Record<string, unknown>> {
  try {
    const parsed = JSON.parse(raw || "[]");
    if (Array.isArray(parsed)) {
      return parsed.filter((d) => d && typeof d === "object") as Array<Record<string, unknown>>;
    }
  } catch {
    // ignore
  }
  return [];
}

export function IntegrationsPage() {
  const qc = useQueryClient();
  const { hasPermission } = useAuth();
  const canResolve = hasPermission(PERMS.INTEGRATIONS_RESOLVE_CONFLICTS);

  const [activeTab, setActiveTab] = useState<string | null>("conflicts");
  const [selectedConflictId, setSelectedConflictId] = useState<string | null>(null);

  const build = useQuery({ queryKey: ["build_info"], queryFn: () => apiFetch<BuildInfo>("/api/system/build_info") });

  const outbound = useQuery({
    queryKey: ["outbound_status"],
    queryFn: () => apiFetch<Record<string, number>>("/api/outbound/status"),
    enabled: !!build.data?.pilot_mode,
  });

  const inboundEvents = useQuery({
    queryKey: ["sync_events"],
    queryFn: () => apiFetch<{ rows: SyncEvent[] }>("/api/integrations/sync_events"),
    enabled: !!build.data?.pilot_mode,
  });

  const deadLetters = useQuery({
    queryKey: ["dead_letters"],
    queryFn: () => apiFetch<{ rows: DeadLetterRow[] }>("/api/integrations/dead_letters"),
    enabled: !!build.data?.pilot_mode,
  });

  const conflicts = useQuery({
    queryKey: ["sync_conflicts"],
    queryFn: () => apiFetch<{ rows: ConflictRow[] }>("/api/integrations/conflicts"),
    enabled: !!build.data?.pilot_mode,
  });

  const selectedConflict = useMemo(
    () => (conflicts.data?.rows || []).find((c) => c.id === selectedConflictId) || null,
    [conflicts.data, selectedConflictId]
  );

  const refreshAll = async () => {
    await qc.invalidateQueries({ queryKey: ["outbound_status"] });
    await qc.invalidateQueries({ queryKey: ["sync_events"] });
    await qc.invalidateQueries({ queryKey: ["dead_letters"] });
    await qc.invalidateQueries({ queryKey: ["sync_conflicts"] });
  };

  const resolveConflict = async (id: string, action: "TRUST_LMS" | "TRUST_LOCAL" | "MANUAL_OVERRIDE") => {
    await apiFetch(`/api/integrations/conflicts/${encodeURIComponent(id)}/resolve`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action, manual_override: action === "MANUAL_OVERRIDE" ? { state: "CLOSED", disposition: "manual_override" } : undefined }),
    });
    notifications.show({ color: "green", message: `Conflict resolved with ${action}` });
    setSelectedConflictId(null);
    await refreshAll();
  };

  const replayDead = async (queueId: string) => {
    await apiFetch(`/api/integrations/dead_letters/${encodeURIComponent(queueId)}/replay`, { method: "POST" });
    notifications.show({ color: "green", message: `Replay queued for ${queueId}` });
    await refreshAll();
  };

  if (!build.data?.pilot_mode) {
    return (
      <Card className="te-data-card">
        <Title order={3}>Integrations</Title>
        <Text c="dimmed">Pilot mode is disabled. Enable `PILOT_MODE=1` to use LMS/CRM reconciliation.</Text>
      </Card>
    );
  }

  return (
    <Stack>
      <ModuleHeader
        title="Integrations & Reconciliation"
        subtitle="Track syncs, replay failures, and resolve LMS/CRM conflicts safely"
        action={<Button variant="light" onClick={refreshAll}>Refresh</Button>}
      />

      <FlowGuide
        title="Reconciliation Flow"
        steps={[
          { title: "Watch Queue", detail: "See outbound/inbound sync status" },
          { title: "Handle Failures", detail: "Replay dead-letter events" },
          { title: "Review Conflicts", detail: "Inspect field-level differences" },
          { title: "Resolve", detail: "Trust LMS, Trust Local, or Manual Override" },
        ]}
      />

      <Tabs value={activeTab} onChange={setActiveTab}>
        <Tabs.List>
          <Tabs.Tab value="outbound">Outbound Queue</Tabs.Tab>
          <Tabs.Tab value="inbound">Inbound Events</Tabs.Tab>
          <Tabs.Tab value="dead">Dead Letters</Tabs.Tab>
          <Tabs.Tab value="conflicts">Conflicts</Tabs.Tab>
        </Tabs.List>

        <Tabs.Panel value="outbound" pt="md">
          <Card className="te-section-card">
            <Group justify="space-between" mb="sm">
              <Title order={4}>Outbound Queue</Title>
              <Badge variant="light">CRM Adapter</Badge>
            </Group>
            <JsonInput value={JSON.stringify(outbound.data || {}, null, 2)} autosize minRows={8} readOnly />
          </Card>
        </Tabs.Panel>

        <Tabs.Panel value="inbound" pt="md">
          <Card className="te-section-card">
            <Title order={4} mb="sm">Inbound LMS Events</Title>
            {(inboundEvents.data?.rows || []).length ? (
              <ScrollArea className="te-table-wrap te-subtle-scroll" offsetScrollbars>
                <Table>
                  <Table.Thead>
                    <Table.Tr>
                      <Table.Th>Time</Table.Th>
                      <Table.Th>Direction</Table.Th>
                      <Table.Th>Status</Table.Th>
                      <Table.Th>Entity</Table.Th>
                      <Table.Th>Attempts</Table.Th>
                      <Table.Th>Error</Table.Th>
                    </Table.Tr>
                  </Table.Thead>
                  <Table.Tbody>
                    {(inboundEvents.data?.rows || []).map((row) => (
                      <Table.Tr key={row.id}>
                        <Table.Td>{dayjs.unix(row.ts).format("DD MMM HH:mm")}</Table.Td>
                        <Table.Td>{row.direction}</Table.Td>
                        <Table.Td>{row.status}</Table.Td>
                        <Table.Td>{row.entity_type}:{row.entity_id}</Table.Td>
                        <Table.Td>{row.attempts}</Table.Td>
                        <Table.Td>{row.last_error || "-"}</Table.Td>
                      </Table.Tr>
                    ))}
                  </Table.Tbody>
                </Table>
              </ScrollArea>
            ) : (
              <EmptyStateCard title="No inbound events" description="Inbound LMS events will appear here once webhook sync starts." />
            )}
          </Card>
        </Tabs.Panel>

        <Tabs.Panel value="dead" pt="md">
          <Card className="te-section-card">
            <Title order={4} mb="sm">Dead Letters</Title>
            {(deadLetters.data?.rows || []).length ? (
              <ScrollArea className="te-table-wrap te-subtle-scroll" offsetScrollbars>
                <Table>
                  <Table.Thead>
                    <Table.Tr>
                      <Table.Th>Queue ID</Table.Th>
                      <Table.Th>Session</Table.Th>
                      <Table.Th>Event</Table.Th>
                      <Table.Th>Attempts</Table.Th>
                      <Table.Th>Updated</Table.Th>
                      <Table.Th>Action</Table.Th>
                    </Table.Tr>
                  </Table.Thead>
                  <Table.Tbody>
                    {(deadLetters.data?.rows || []).map((row) => (
                      <Table.Tr key={row.queue_id}>
                        <Table.Td>{row.queue_id}</Table.Td>
                        <Table.Td>{row.session_id}</Table.Td>
                        <Table.Td>{row.event_type}</Table.Td>
                        <Table.Td>{row.attempts}</Table.Td>
                        <Table.Td>{dayjs.unix(row.updated_ts).format("DD MMM HH:mm")}</Table.Td>
                        <Table.Td>
                          {canResolve ? (
                            <Button size="xs" variant="light" onClick={() => replayDead(row.queue_id)}>
                              Replay
                            </Button>
                          ) : (
                            "-"
                          )}
                        </Table.Td>
                      </Table.Tr>
                    ))}
                  </Table.Tbody>
                </Table>
              </ScrollArea>
            ) : (
              <EmptyStateCard title="No dead letters" description="Connector retries are healthy right now. Failed events will surface here for replay." />
            )}
          </Card>
        </Tabs.Panel>

        <Tabs.Panel value="conflicts" pt="md">
          <Card className="te-section-card">
            <Title order={4} mb="sm">Conflicts</Title>
            {(conflicts.data?.rows || []).length ? (
              <ScrollArea className="te-table-wrap te-subtle-scroll" offsetScrollbars>
                <Table>
                  <Table.Thead>
                    <Table.Tr>
                      <Table.Th>Time</Table.Th>
                      <Table.Th>Entity</Table.Th>
                      <Table.Th>Status</Table.Th>
                      <Table.Th>Diff Summary</Table.Th>
                      <Table.Th>Action</Table.Th>
                    </Table.Tr>
                  </Table.Thead>
                  <Table.Tbody>
                    {(conflicts.data?.rows || []).map((row) => (
                      <Table.Tr key={row.id}>
                        <Table.Td>{dayjs.unix(row.ts).format("DD MMM HH:mm")}</Table.Td>
                        <Table.Td>{row.entity_type}:{row.entity_id}</Table.Td>
                        <Table.Td>{row.status}</Table.Td>
                        <Table.Td>{parseDiffs(row.field_diffs_json).length} field diffs</Table.Td>
                        <Table.Td>
                          <Button size="xs" variant="light" onClick={() => setSelectedConflictId(row.id)}>
                            Review
                          </Button>
                        </Table.Td>
                      </Table.Tr>
                    ))}
                  </Table.Tbody>
                </Table>
              </ScrollArea>
            ) : (
              <EmptyStateCard title="No open conflicts" description="No data mismatches are currently waiting for reconciliation decisions." />
            )}
          </Card>
        </Tabs.Panel>
      </Tabs>

      <Modal opened={!!selectedConflict} onClose={() => setSelectedConflictId(null)} title="Resolve Conflict" size="lg">
        {selectedConflict ? (
          <Stack>
            <Text size="sm">Entity: {selectedConflict.entity_type}:{selectedConflict.entity_id}</Text>
            <Text size="sm">Status: {selectedConflict.status}</Text>
            <ScrollArea className="te-table-wrap te-subtle-scroll" offsetScrollbars>
              <Table>
                <Table.Thead>
                  <Table.Tr>
                    <Table.Th>Field</Table.Th>
                    <Table.Th>Local</Table.Th>
                    <Table.Th>Inbound</Table.Th>
                    <Table.Th>Reason</Table.Th>
                  </Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {parseDiffs(selectedConflict.field_diffs_json).map((d, idx) => (
                    <Table.Tr key={idx}>
                      <Table.Td>{String(d.field || "-")}</Table.Td>
                      <Table.Td>{typeof d.local === "object" ? JSON.stringify(d.local) : String(d.local ?? "-")}</Table.Td>
                      <Table.Td>{typeof d.inbound === "object" ? JSON.stringify(d.inbound) : String(d.inbound ?? "-")}</Table.Td>
                      <Table.Td>{String(d.reason || "-")}</Table.Td>
                    </Table.Tr>
                  ))}
                </Table.Tbody>
              </Table>
            </ScrollArea>
            {canResolve ? (
              <Group justify="flex-end">
                <Button variant="light" onClick={() => resolveConflict(selectedConflict.id, "TRUST_LMS")}>TRUST_LMS</Button>
                <Button variant="light" onClick={() => resolveConflict(selectedConflict.id, "TRUST_LOCAL")}>TRUST_LOCAL</Button>
                <Button color="orange" onClick={() => resolveConflict(selectedConflict.id, "MANUAL_OVERRIDE")}>MANUAL_OVERRIDE</Button>
              </Group>
            ) : (
              <Text c="dimmed" size="sm">Read-only: you do not have conflict resolution permission.</Text>
            )}
          </Stack>
        ) : null}
      </Modal>
    </Stack>
  );
}
