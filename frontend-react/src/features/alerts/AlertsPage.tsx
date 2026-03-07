import {
  Badge,
  Button,
  Card,
  Divider,
  Group,
  JsonInput,
  ScrollArea,
  Select,
  SimpleGrid,
  Stack,
  Switch,
  Table,
  Tabs,
  Text,
  TextInput,
  Title,
} from "@mantine/core";
import dayjs from "dayjs";
import { notifications } from "@mantine/notifications";
import { useEffect, useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ShieldAlert } from "lucide-react";

import { apiFetch, toQuery } from "../../api/client";
import { useAuth } from "../../auth/AuthProvider";
import { PERMS } from "../../auth/roles";
import { FlowGuide } from "../../components/FlowGuide";
import { ModuleHeader } from "../../components/ModuleHeader";
import { EmptyStateCard } from "../../components/EmptyStateCard";
import type { AlertRow, RuleRow } from "../../types/api";

interface ComplianceViolation {
  id: number;
  ts: number;
  session_id: string;
  rule_code: string;
  severity: string;
  detail: string;
  excerpt?: string;
}

export function AlertsPage() {
  const qc = useQueryClient();
  const { hasPermission } = useAuth();
  const canMutate = hasPermission(PERMS.ALERTS_MUTATE);
  const canEditRules = hasPermission(PERMS.ALERT_RULES_EDIT);

  const [statusFilter, setStatusFilter] = useState("");
  const [typeFilter, setTypeFilter] = useState("");
  const [severityFilter, setSeverityFilter] = useState("");
  const [selectedAlertId, setSelectedAlertId] = useState<string | null>(null);
  const [assignee, setAssignee] = useState("");

  const [ruleId, setRuleId] = useState("");
  const [ruleName, setRuleName] = useState("");
  const [ruleType, setRuleType] = useState("PTP_MISS");
  const [ruleEnabled, setRuleEnabled] = useState(true);
  const [thresholdJson, setThresholdJson] = useState("{}");
  const [routingJson, setRoutingJson] = useState('{"channels":["inapp"]}');

  const alertsQuery = useQuery({
    queryKey: ["alerts", statusFilter, typeFilter, severityFilter],
    queryFn: () =>
      apiFetch<{ rows: AlertRow[]; total: number }>(
        `/api/alerts${toQuery({ status: statusFilter, type: typeFilter, severity: severityFilter, page: 1, page_size: 80 })}`
      ),
    refetchInterval: 10_000,
  });

  const alertDetail = useQuery({
    queryKey: ["alert_detail", selectedAlertId],
    queryFn: () => apiFetch<AlertRow>(`/api/alerts/${encodeURIComponent(selectedAlertId || "")}`),
    enabled: !!selectedAlertId,
  });

  const rulesQuery = useQuery({ queryKey: ["alert_rules"], queryFn: () => apiFetch<{ rows: RuleRow[] }>("/api/alert_rules") });
  const complianceQuery = useQuery({
    queryKey: ["compliance_violations"],
    queryFn: () => apiFetch<{ rows: ComplianceViolation[] }>("/api/compliance/violations"),
    refetchInterval: 10_000,
  });

  useEffect(() => {
    if (!selectedAlertId && alertsQuery.data?.rows?.length) {
      setSelectedAlertId(alertsQuery.data.rows[0].id);
    }
  }, [alertsQuery.data, selectedAlertId]);

  const selectedRule = useMemo(() => rulesQuery.data?.rows?.find((r) => r.id === ruleId), [rulesQuery.data, ruleId]);

  useEffect(() => {
    if (!selectedRule) return;
    setRuleName(selectedRule.name || "");
    setRuleType(selectedRule.type || "PTP_MISS");
    setRuleEnabled(!!selectedRule.enabled);
    setThresholdJson(selectedRule.threshold_json || "{}");
    setRoutingJson(selectedRule.routing_json || '{"channels":["inapp"]}');
  }, [selectedRule]);

  const refresh = async () => {
    await qc.invalidateQueries({ queryKey: ["alerts"] });
    await qc.invalidateQueries({ queryKey: ["alert_detail"] });
    await qc.invalidateQueries({ queryKey: ["alert_rules"] });
    await qc.invalidateQueries({ queryKey: ["compliance_violations"] });
  };

  const onAck = async () => {
    if (!selectedAlertId) return;
    await apiFetch(`/api/alerts/${encodeURIComponent(selectedAlertId)}/ack`, { method: "POST" });
    notifications.show({ color: "green", message: "Alert acknowledged" });
    await refresh();
  };

  const onAssign = async () => {
    if (!selectedAlertId || !assignee.trim()) return;
    await apiFetch(`/api/alerts/${encodeURIComponent(selectedAlertId)}/assign`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ assignee: assignee.trim() }),
    });
    notifications.show({ color: "green", message: "Alert assigned" });
    await refresh();
  };

  const onResolve = async () => {
    if (!selectedAlertId) return;
    await apiFetch(`/api/alerts/${encodeURIComponent(selectedAlertId)}/resolve`, { method: "POST" });
    notifications.show({ color: "green", message: "Alert resolved" });
    await refresh();
  };

  const onEvaluate = async () => {
    await apiFetch("/api/alerts/evaluate", { method: "POST" });
    notifications.show({ color: "green", message: "Rules evaluated" });
    await refresh();
  };

  const onToggleRule = async (id: string, enabled: boolean) => {
    await apiFetch(`/api/alert_rules/${encodeURIComponent(id)}/toggle`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled }),
    });
    await refresh();
  };

  const onSaveRule = async () => {
    try {
      const threshold = JSON.parse(thresholdJson || "{}");
      const routing = JSON.parse(routingJson || "{}");
      await apiFetch("/api/alert_rules", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          id: ruleId || undefined,
          name: ruleName || "Rule",
          type: ruleType,
          enabled: ruleEnabled,
          threshold_json: threshold,
          routing_json: routing,
        }),
      });
      notifications.show({ color: "green", message: "Rule saved" });
      await refresh();
    } catch (err) {
      notifications.show({ color: "red", message: `Invalid JSON: ${String(err)}` });
    }
  };

  return (
    <Stack>
      <ModuleHeader
        title="Alerts & Compliance"
        subtitle="Single inbox for alerts, ownership, resolution, and compliance control"
        action={
          <Group>
            <Button variant="light" onClick={refresh}>Refresh</Button>
            {canMutate ? <Button onClick={onEvaluate}>Evaluate Rules</Button> : null}
          </Group>
        }
      />

      <FlowGuide
        title="Alerts Triage Flow"
        steps={[
          { title: "Filter Inbox", detail: "Status, type, severity filters" },
          { title: "Open Detail", detail: "Review payload + linked entity" },
          { title: "Own It", detail: "ACK or assign to responsible user" },
          { title: "Resolve + Tune", detail: "Close alert and adjust rules if needed" },
        ]}
      />

      <Tabs defaultValue="inbox">
        <Tabs.List>
          <Tabs.Tab value="inbox">Alerts Inbox</Tabs.Tab>
          <Tabs.Tab value="rules">Rules</Tabs.Tab>
          <Tabs.Tab value="cases">Compliance Cases</Tabs.Tab>
        </Tabs.List>

        <Tabs.Panel value="inbox" pt="md">
          <Card className="te-section-card">
            <SimpleGrid cols={{ base: 1, md: 4 }} mb="sm">
              <Select label="Status" value={statusFilter} onChange={(v) => setStatusFilter(v || "")} data={["", "OPEN", "ACKED", "RESOLVED"].map((v) => ({ value: v, label: v || "All" }))} />
              <Select
                label="Type"
                value={typeFilter}
                onChange={(v) => setTypeFilter(v || "")}
                data={["", "PTP_MISS", "SLA_BREACH", "COMPLIANCE_VIOLATION", "COMPLIANCE_BLOCK", "ESCALATION_SPIKE"].map((v) => ({ value: v, label: v || "All" }))}
              />
              <Select label="Severity" value={severityFilter} onChange={(v) => setSeverityFilter(v || "")} data={["", "low", "medium", "high", "critical"].map((v) => ({ value: v, label: v || "All" }))} />
            </SimpleGrid>

            <SimpleGrid cols={{ base: 1, lg: 2 }}>
              <Card withBorder className="te-data-card">
                <Title order={4} mb="sm">Alert List</Title>
                {(alertsQuery.data?.rows || []).length ? (
                  <ScrollArea className="te-table-wrap te-subtle-scroll" offsetScrollbars>
                    <Table>
                      <Table.Thead>
                        <Table.Tr>
                          <Table.Th>Time</Table.Th>
                          <Table.Th>Type</Table.Th>
                          <Table.Th>Severity</Table.Th>
                          <Table.Th>Status</Table.Th>
                        </Table.Tr>
                      </Table.Thead>
                      <Table.Tbody>
                        {(alertsQuery.data?.rows || []).map((row) => (
                          <Table.Tr
                            key={row.id}
                            onClick={() => setSelectedAlertId(row.id)}
                            style={{ cursor: "pointer", outline: selectedAlertId === row.id ? "1px solid #125dff" : "none" }}
                          >
                            <Table.Td>{dayjs.unix(row.ts).format("DD MMM HH:mm")}</Table.Td>
                            <Table.Td>{row.type}</Table.Td>
                            <Table.Td>
                              <Badge color={row.severity === "high" || row.severity === "critical" ? "red" : row.severity === "medium" ? "orange" : "blue"}>
                                {row.severity}
                              </Badge>
                            </Table.Td>
                            <Table.Td>{row.status}</Table.Td>
                          </Table.Tr>
                        ))}
                      </Table.Tbody>
                    </Table>
                  </ScrollArea>
                ) : (
                  <EmptyStateCard title="No alerts found" description="Current filters returned no alerts. Try broadening status/type/severity or run evaluation." />
                )}
              </Card>

              <Card withBorder className="te-data-card">
                <Title order={4} mb="sm">Alert Detail</Title>
                {alertDetail.data ? (
                  <Stack>
                    <Text fw={600}>{alertDetail.data.message}</Text>
                    <Text size="sm">Entity: {alertDetail.data.entity_type}:{alertDetail.data.entity_id}</Text>
                    <Text size="sm">Created: {dayjs.unix(alertDetail.data.ts).format("DD MMM YYYY HH:mm:ss")}</Text>
                    <Text size="sm">Assigned: {alertDetail.data.assigned_to || "-"}</Text>
                    <Text size="sm">Status: {alertDetail.data.status}</Text>
                    <details>
                      <summary>Raw payload</summary>
                      <JsonInput value={alertDetail.data.payload_json || "{}"} readOnly autosize minRows={4} />
                    </details>
                    {canMutate ? (
                      <Group>
                        <Button size="xs" onClick={onAck}>ACK</Button>
                        <TextInput size="xs" placeholder="assignee" value={assignee} onChange={(e) => setAssignee(e.currentTarget.value)} />
                        <Button size="xs" variant="light" onClick={onAssign}>Assign</Button>
                        <Button size="xs" color="green" onClick={onResolve}>Resolve</Button>
                      </Group>
                    ) : null}
                  </Stack>
                ) : (
                  <Text c="dimmed">Select an alert row</Text>
                )}
              </Card>
            </SimpleGrid>
          </Card>
        </Tabs.Panel>

        <Tabs.Panel value="rules" pt="md">
          <Card className="te-section-card">
            <Title order={4} mb="sm">Rules Editor</Title>
            <ScrollArea className="te-table-wrap te-subtle-scroll" offsetScrollbars mb="md">
              <Table>
                <Table.Thead>
                  <Table.Tr>
                    <Table.Th>ID</Table.Th>
                    <Table.Th>Name</Table.Th>
                    <Table.Th>Type</Table.Th>
                    <Table.Th>Enabled</Table.Th>
                    <Table.Th>Toggle</Table.Th>
                  </Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {(rulesQuery.data?.rows || []).map((row) => (
                    <Table.Tr key={row.id} onClick={() => setRuleId(row.id)} style={{ cursor: "pointer" }}>
                      <Table.Td>{row.id}</Table.Td>
                      <Table.Td>{row.name}</Table.Td>
                      <Table.Td>{row.type}</Table.Td>
                      <Table.Td>{row.enabled ? "Yes" : "No"}</Table.Td>
                      <Table.Td>
                        <Switch checked={!!row.enabled} disabled={!canEditRules} onChange={(e) => onToggleRule(row.id, e.currentTarget.checked)} />
                      </Table.Td>
                    </Table.Tr>
                  ))}
                </Table.Tbody>
              </Table>
            </ScrollArea>

            <Divider my="sm" />
            <SimpleGrid cols={{ base: 1, md: 2 }}>
              <TextInput label="Rule ID (blank=create)" value={ruleId} onChange={(e) => setRuleId(e.currentTarget.value)} disabled={!canEditRules} />
              <TextInput label="Name" value={ruleName} onChange={(e) => setRuleName(e.currentTarget.value)} disabled={!canEditRules} />
              <Select label="Type" value={ruleType} onChange={(v) => setRuleType(v || "PTP_MISS")} data={["PTP_MISS", "SLA_BREACH", "COMPLIANCE_VIOLATION", "COMPLIANCE_BLOCK", "ESCALATION_SPIKE"]} disabled={!canEditRules} />
              <Switch label="Enabled" checked={ruleEnabled} onChange={(e) => setRuleEnabled(e.currentTarget.checked)} disabled={!canEditRules} />
            </SimpleGrid>
            <JsonInput label="threshold_json" value={thresholdJson} onChange={setThresholdJson} autosize minRows={6} readOnly={!canEditRules} />
            <JsonInput label="routing_json" value={routingJson} onChange={setRoutingJson} autosize minRows={6} readOnly={!canEditRules} />
            {canEditRules ? <Button onClick={onSaveRule}>Save Rule</Button> : null}
          </Card>
        </Tabs.Panel>

        <Tabs.Panel value="cases" pt="md">
          <Card className="te-section-card">
            <Group justify="space-between" mb="sm">
              <Title order={4}>Compliance Violation Feed</Title>
              <Badge leftSection={<ShieldAlert size={12} />}>Realtime</Badge>
            </Group>
            {(complianceQuery.data?.rows || []).length ? (
              <ScrollArea className="te-table-wrap te-subtle-scroll" offsetScrollbars>
                <Table>
                  <Table.Thead>
                    <Table.Tr>
                      <Table.Th>Time</Table.Th>
                      <Table.Th>Session</Table.Th>
                      <Table.Th>Rule</Table.Th>
                      <Table.Th>Severity</Table.Th>
                      <Table.Th>Detail</Table.Th>
                    </Table.Tr>
                  </Table.Thead>
                  <Table.Tbody>
                    {(complianceQuery.data?.rows || []).map((row) => (
                      <Table.Tr key={row.id}>
                        <Table.Td>{dayjs.unix(row.ts).format("DD MMM HH:mm:ss")}</Table.Td>
                        <Table.Td>{row.session_id}</Table.Td>
                        <Table.Td>{row.rule_code}</Table.Td>
                        <Table.Td>
                          <Badge color={row.severity === "high" || row.severity === "critical" ? "red" : "orange"}>{row.severity}</Badge>
                        </Table.Td>
                        <Table.Td>
                          <Text size="sm">{row.detail}</Text>
                          {row.excerpt ? <Text size="xs" c="dimmed">{row.excerpt}</Text> : null}
                        </Table.Td>
                      </Table.Tr>
                    ))}
                  </Table.Tbody>
                </Table>
              </ScrollArea>
            ) : (
              <EmptyStateCard title="No compliance violations" description="No violations are currently recorded for the selected observation window." />
            )}
          </Card>
        </Tabs.Panel>
      </Tabs>
    </Stack>
  );
}
