import { Badge, Card, Grid, Group, Loader, Progress, ScrollArea, Select, SimpleGrid, Stack, Table, Text, Title } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useMemo, useState } from "react";

import { apiFetch, toQuery } from "../../api/client";
import { EmptyStateCard } from "../../components/EmptyStateCard";
import { ModuleHeader } from "../../components/ModuleHeader";
import type { BuildInfo, CampaignRow } from "../../types/api";

interface MetricsResponse {
  sessions_today: number;
  ptp_count: number;
  callback_count: number;
  escalations: number;
  retries_pending: number;
  avg_handle_seconds?: number | null;
  conversion_by_campaign?: Record<string, { total: number; completed: number; rate: number }>;
  bucket_heatmap?: Record<string, number>;
  expected_recovery_amount?: number;
  sla_breaches?: number;
  accounts_assigned?: number;
  accounts_contacted?: number;
  contact_rate_pct?: number;
  followups_scheduled_total?: number;
  followups_pending_total?: number;
  followups_sent_total?: number;
  followups_missed_total?: number;
  followups_due_today?: number;
  followups_completed_today?: number;
  followup_discipline_rate_pct?: number;
  ptp_miss_count?: number;
  ptp_miss_open_alerts?: number;
  queue_snapshot?: Record<string, number>;
  ptp_rate_by_bucket?: Record<string, { total: number; ptp: number; rate: number }>;
}

interface RollForwardResponse {
  buckets: string[];
  matrix: Record<string, Record<string, number>>;
  total_transitions: number;
  roll_forward_count: number;
  roll_forward_pct: number;
  window_days: number;
}

interface RecoveryResponse {
  dates: string[];
  amounts: number[];
  total_recovered: number;
  portfolio_value: number;
  recovery_rate_pct: number;
  reconciliation: Array<{ date?: string; session_id?: string; customer_id?: string; amount?: number }>;
}

interface AgentMetric {
  rank: number;
  display_name: string;
  total_calls: number;
  connect_rate_pct: number;
  avg_handle_time_s: number;
  ptp_count: number;
  ptp_conversion_pct: number;
  escalations: number;
  compliance_violations: number;
}

const BUCKETS = ["1-30", "31-60", "61-90", "90+"] as const;

function kpi(label: string, value: string | number, hint?: string) {
  return (
    <Card className="te-kpi-card">
      <Stack gap={2}>
        <Text size="sm" c="dimmed">
          {label}
        </Text>
        <Title order={3}>{value}</Title>
        {hint ? (
          <Text size="xs" c="dimmed">
            {hint}
          </Text>
        ) : null}
      </Stack>
    </Card>
  );
}

function rupees(n: number): string {
  try {
    return new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 }).format(n || 0);
  } catch {
    return `INR ${Math.round(n || 0)}`;
  }
}

function percent(n?: number | null): string {
  return `${Number(n || 0).toFixed(1)}%`;
}

function heatColor(value: number, max: number): string {
  if (!value || max <= 0) {
    return "rgba(18, 93, 255, 0.06)";
  }
  const alpha = 0.12 + (value / max) * 0.58;
  return `rgba(18, 93, 255, ${Math.min(0.7, alpha).toFixed(2)})`;
}

const LIVE_REFRESH_MS = 10_000;

export function OverviewPage() {
  const [campaignId, setCampaignId] = useState("");

  const metrics = useQuery({
    queryKey: ["metrics", campaignId],
    queryFn: () => apiFetch<MetricsResponse>(`/api/metrics${toQuery({ campaign_id: campaignId })}`),
    refetchInterval: LIVE_REFRESH_MS,
  });
  const campaigns = useQuery({
    queryKey: ["campaigns"],
    queryFn: () => apiFetch<{ rows: CampaignRow[] }>("/api/campaigns"),
    refetchInterval: LIVE_REFRESH_MS,
  });
  const build = useQuery({ queryKey: ["build_info"], queryFn: () => apiFetch<BuildInfo>("/api/system/build_info") });
  const rollForward = useQuery({
    queryKey: ["metrics_roll_forward", campaignId],
    queryFn: () => apiFetch<RollForwardResponse>(`/api/metrics/roll-forward${toQuery({ campaign_id: campaignId, days: 30 })}`),
    refetchInterval: LIVE_REFRESH_MS,
  });
  const recovery = useQuery({
    queryKey: ["metrics_recovery", campaignId],
    queryFn: () => apiFetch<RecoveryResponse>(`/api/metrics/recovery${toQuery({ campaign_id: campaignId, days: 30 })}`),
    refetchInterval: LIVE_REFRESH_MS,
  });
  const agents = useQuery({
    queryKey: ["metrics_agents", campaignId],
    queryFn: () => apiFetch<{ agents: AgentMetric[] }>(`/api/metrics/agents${toQuery({ campaign_id: campaignId })}`),
    refetchInterval: LIVE_REFRESH_MS,
  });

  const selectedCampaign = useMemo(
    () => (campaigns.data?.rows || []).find((row) => row.campaign_id === campaignId) || null,
    [campaignId, campaigns.data],
  );

  if (metrics.isLoading || campaigns.isLoading) {
    return (
      <Group justify="center" py="xl">
        <Loader />
      </Group>
    );
  }

  if (!metrics.data) {
    return <Text c="red">Unable to load dashboard metrics.</Text>;
  }

  const m = metrics.data;
  const bucketData = BUCKETS.map((bucket) => ({
    bucket,
    exposure: Number(m.bucket_heatmap?.[bucket] || 0),
    ptpRate: Number(m.ptp_rate_by_bucket?.[bucket]?.rate || 0),
  }));
  const followupData = [
    { label: "Pending", value: Number(m.followups_pending_total || 0) },
    { label: "Sent", value: Number(m.followups_sent_total || 0) },
    { label: "Missed", value: Number(m.followups_missed_total || 0) },
  ];
  const recoveryData = (recovery.data?.dates || []).map((date, index) => ({
    date,
    amount: Number(recovery.data?.amounts?.[index] || 0),
  }));
  const queueRows = Object.entries(m.queue_snapshot || {}).map(([state, count]) => ({
    state: state.replaceAll("_", " "),
    count: Number(count || 0),
  }));
  const matrixBuckets = rollForward.data?.buckets || [];
  const matrixValues = matrixBuckets.flatMap((from) => matrixBuckets.map((to) => Number(rollForward.data?.matrix?.[from]?.[to] || 0)));
  const maxMatrixValue = Math.max(0, ...matrixValues);
  const containmentRate =
    rollForward.data && rollForward.data.total_transitions > 0 ? 100 - Number(rollForward.data.roll_forward_pct || 0) : null;

  return (
    <Stack gap="md">
      <ModuleHeader
        title="Early Bucket Control Room"
        subtitle="Show that uploaded portfolios are tracked, followed up, and contained before they roll forward"
        badge="Live"
        action={
          <Group>
            <Select
              value={campaignId}
              onChange={(value) => setCampaignId(value || "")}
              placeholder="All campaigns"
              data={[{ value: "", label: "All campaigns" }, ...(campaigns.data?.rows || []).map((row) => ({ value: row.campaign_id, label: row.name || row.campaign_id }))]}
              w={240}
            />
            <Badge variant="light">Build {build.data?.static_token || "-"}</Badge>
          </Group>
        }
      />

      <Card className="te-data-card">
        <Group justify="space-between" wrap="wrap">
          <div>
            <Text size="xs" tt="uppercase" fw={700} c="dimmed">
              Demo Story
            </Text>
            <Title order={4}>Upload portfolio, capture commitment, prove follow-through discipline.</Title>
            <Text size="sm" c="dimmed" mt={4}>
              {selectedCampaign
                ? `Current scope: ${selectedCampaign.name} (${selectedCampaign.campaign_id})`
                : "Use the campaign filter to isolate the buyer's uploaded portfolio during the demo."}
            </Text>
          </div>
          <Badge variant="outline" color="blue">
            Focus: Missed PTP Control
          </Badge>
        </Group>
      </Card>

      <Grid>
        <Grid.Col span={{ base: 12, md: 3 }}>{kpi("Accounts Assigned", Number(m.accounts_assigned || 0), "Current queue in scope")}</Grid.Col>
        <Grid.Col span={{ base: 12, md: 3 }}>{kpi("Contact Coverage", percent(m.contact_rate_pct), `${Number(m.accounts_contacted || 0)} reached`)}</Grid.Col>
        <Grid.Col span={{ base: 12, md: 3 }}>{kpi("PTP Captured", Number(m.ptp_count || 0), `${Number(m.callback_count || 0)} callbacks logged`)}</Grid.Col>
        <Grid.Col span={{ base: 12, md: 3 }}>
          {kpi(
            "Follow-up Discipline",
            percent(m.followup_discipline_rate_pct),
            `${Number(m.followups_completed_today || 0)}/${Number(m.followups_due_today || 0)} due today closed`,
          )}
        </Grid.Col>
        <Grid.Col span={{ base: 12, md: 3 }}>{kpi("Missed PTP Alerts", Number(m.ptp_miss_open_alerts || 0), `${Number(m.ptp_miss_count || 0)} misses processed`)}</Grid.Col>
        <Grid.Col span={{ base: 12, md: 3 }}>
          {kpi(
            "Containment Rate",
            containmentRate == null ? "n/a" : percent(containmentRate),
            rollForward.data?.total_transitions
              ? `${rollForward.data.roll_forward_count} roll-forwards in ${rollForward.data.total_transitions} tracked transitions`
              : "Builds once DPD snapshots accumulate",
          )}
        </Grid.Col>
        <Grid.Col span={{ base: 12, md: 3 }}>{kpi("Expected Recovery", rupees(Number(m.expected_recovery_amount || 0)), `${Number(m.queue_snapshot?.PTP || 0)} active PTP accounts`)}</Grid.Col>
        <Grid.Col span={{ base: 12, md: 3 }}>
          {kpi(
            "Recovery Rate",
            percent(recovery.data?.recovery_rate_pct),
            recovery.data ? `${rupees(Number(recovery.data.total_recovered || 0))} realized over 30 days` : "No recovery data yet",
          )}
        </Grid.Col>
      </Grid>

      <Grid>
        <Grid.Col span={{ base: 12, lg: 6 }}>
          <Card className="te-data-card">
            <Group justify="space-between" mb="sm">
              <Title order={4}>PTP Discipline Engine</Title>
              <Badge variant="outline">Operational</Badge>
            </Group>
            <Text size="sm" c="dimmed" mb="md">
              This is the proof that commitment handling is disciplined, not just high-volume.
            </Text>
            <div style={{ height: 260 }}>
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={followupData}>
                  <CartesianGrid strokeDasharray="4 4" />
                  <XAxis dataKey="label" />
                  <YAxis allowDecimals={false} />
                  <Tooltip />
                  <Bar dataKey="value" fill="#125dff" radius={[8, 8, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
            <SimpleGrid cols={{ base: 1, md: 3 }} mt="md">
              <Card>
                <Text size="sm" c="dimmed">
                  Due Today
                </Text>
                <Title order={4}>{Number(m.followups_due_today || 0)}</Title>
              </Card>
              <Card>
                <Text size="sm" c="dimmed">
                  Total Scheduled
                </Text>
                <Title order={4}>{Number(m.followups_scheduled_total || 0)}</Title>
              </Card>
              <Card>
                <Text size="sm" c="dimmed">
                  Queue SLA Breaches
                </Text>
                <Title order={4}>{Number(m.sla_breaches || 0)}</Title>
              </Card>
            </SimpleGrid>
          </Card>
        </Grid.Col>

        <Grid.Col span={{ base: 12, lg: 6 }}>
          <Card className="te-data-card">
            <Group justify="space-between" mb="sm">
              <Title order={4}>Bucket Pressure And Conversion</Title>
              <Badge variant="outline">DPD Lens</Badge>
            </Group>
            <div style={{ height: 260 }}>
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={bucketData}>
                  <CartesianGrid strokeDasharray="4 4" />
                  <XAxis dataKey="bucket" />
                  <YAxis yAxisId="left" allowDecimals={false} />
                  <YAxis yAxisId="right" orientation="right" />
                  <Tooltip />
                  <Bar yAxisId="left" dataKey="exposure" fill="#125dff" radius={[8, 8, 0, 0]} />
                  <Bar yAxisId="right" dataKey="ptpRate" fill="#14a44d" radius={[8, 8, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
            <ScrollArea className="te-table-wrap te-subtle-scroll" offsetScrollbars mt="md">
              <Table>
                <Table.Thead>
                  <Table.Tr>
                    <Table.Th>Bucket</Table.Th>
                    <Table.Th>Accounts</Table.Th>
                    <Table.Th>PTP Conversion</Table.Th>
                  </Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {bucketData.map((row) => (
                    <Table.Tr key={row.bucket}>
                      <Table.Td>{row.bucket}</Table.Td>
                      <Table.Td>{row.exposure}</Table.Td>
                      <Table.Td>{percent(row.ptpRate)}</Table.Td>
                    </Table.Tr>
                  ))}
                </Table.Tbody>
              </Table>
            </ScrollArea>
          </Card>
        </Grid.Col>
      </Grid>

      <Card className="te-data-card">
        <Group justify="space-between" mb="sm">
          <div>
            <Title order={4}>Roll-Forward Heatmap</Title>
            <Text size="sm" c="dimmed">
              The metric this buyer will care about once missed PTPs start appearing.
            </Text>
          </div>
          <Badge variant="outline">30-day window</Badge>
        </Group>
        {matrixBuckets.length && rollForward.data?.total_transitions ? (
          <ScrollArea className="te-table-wrap te-subtle-scroll" offsetScrollbars>
            <Table>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>From \ To</Table.Th>
                  {matrixBuckets.map((bucket) => (
                    <Table.Th key={bucket}>{bucket}</Table.Th>
                  ))}
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {matrixBuckets.map((from) => (
                  <Table.Tr key={from}>
                    <Table.Td fw={700}>{from}</Table.Td>
                    {matrixBuckets.map((to) => {
                      const value = Number(rollForward.data?.matrix?.[from]?.[to] || 0);
                      return (
                        <Table.Td key={`${from}-${to}`} style={{ background: heatColor(value, maxMatrixValue) }}>
                          {value || "-"}
                        </Table.Td>
                      );
                    })}
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          </ScrollArea>
        ) : (
          <EmptyStateCard title="No roll-forward history yet" description="Run calls or save manual commitments to accumulate DPD transition history for this view." />
        )}
      </Card>

      <Grid>
        <Grid.Col span={{ base: 12, lg: 7 }}>
          <Card className="te-data-card">
            <Group justify="space-between" mb="sm">
              <Title order={4}>Recovery Trend</Title>
              <Badge variant="outline">Actual payments</Badge>
            </Group>
            {recoveryData.length ? (
              <div style={{ height: 280 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={recoveryData}>
                    <CartesianGrid strokeDasharray="4 4" />
                    <XAxis dataKey="date" minTickGap={24} />
                    <YAxis />
                    <Tooltip formatter={(value) => rupees(Number(value || 0))} />
                    <Line type="monotone" dataKey="amount" stroke="#125dff" strokeWidth={3} dot={false} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            ) : (
              <EmptyStateCard title="No realized recovery yet" description="Successful payment captures will populate the recovery trend and reconciliation trail here." />
            )}
          </Card>
        </Grid.Col>

        <Grid.Col span={{ base: 12, lg: 5 }}>
          <Card className="te-data-card">
            <Group justify="space-between" mb="sm">
              <Title order={4}>Agent Leaderboard</Title>
              <Badge variant="outline">Collections desk</Badge>
            </Group>
            {(agents.data?.agents || []).length ? (
              <ScrollArea className="te-table-wrap te-subtle-scroll" offsetScrollbars>
                <Table>
                  <Table.Thead>
                    <Table.Tr>
                      <Table.Th>Agent</Table.Th>
                      <Table.Th>PTP Conv.</Table.Th>
                      <Table.Th>Calls</Table.Th>
                      <Table.Th>Esc.</Table.Th>
                    </Table.Tr>
                  </Table.Thead>
                  <Table.Tbody>
                    {(agents.data?.agents || []).slice(0, 5).map((row) => (
                      <Table.Tr key={`${row.rank}-${row.display_name}`}>
                        <Table.Td>
                          <Stack gap={2}>
                            <Text fw={600}>{row.display_name}</Text>
                            <Text size="xs" c="dimmed">
                              AHT {Number(row.avg_handle_time_s || 0).toFixed(0)}s
                            </Text>
                          </Stack>
                        </Table.Td>
                        <Table.Td>
                          <Group gap="xs">
                            <Progress value={Math.min(100, Math.max(0, Number(row.ptp_conversion_pct || 0)))} style={{ flex: 1 }} />
                            <Text size="sm">{percent(row.ptp_conversion_pct)}</Text>
                          </Group>
                        </Table.Td>
                        <Table.Td>{row.total_calls}</Table.Td>
                        <Table.Td>{row.escalations}</Table.Td>
                      </Table.Tr>
                    ))}
                  </Table.Tbody>
                </Table>
              </ScrollArea>
            ) : (
              <EmptyStateCard title="No agent history yet" description="Once live or manual commitments are logged, the leaderboard will show conversion, quality, and escalation behavior." />
            )}
          </Card>
        </Grid.Col>
      </Grid>

      <Grid>
        <Grid.Col span={{ base: 12, lg: 6 }}>
          <Card className="te-data-card">
            <Group justify="space-between" mb="sm">
              <Title order={4}>Queue Snapshot</Title>
              <Text size="sm" c="dimmed">
                What the operations team is working right now
              </Text>
            </Group>
            {queueRows.length ? (
              <div style={{ height: 240 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={queueRows}>
                    <CartesianGrid strokeDasharray="4 4" />
                    <XAxis dataKey="state" minTickGap={12} />
                    <YAxis allowDecimals={false} />
                    <Tooltip />
                    <Bar dataKey="count" fill="#0b7fab" radius={[8, 8, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            ) : (
              <EmptyStateCard title="No queue rows yet" description="Launch a campaign from Portfolios to populate the operational queue." />
            )}
          </Card>
        </Grid.Col>

        <Grid.Col span={{ base: 12, lg: 6 }}>
          <Card className="te-data-card">
            <Group justify="space-between" mb="sm">
              <Title order={4}>Campaign Performance</Title>
              <Text size="sm" c="dimmed">
                Launch-to-completion progress by campaign
              </Text>
            </Group>
            {(campaigns.data?.rows || []).length ? (
              <ScrollArea className="te-table-wrap te-subtle-scroll" offsetScrollbars>
                <Table>
                  <Table.Thead>
                    <Table.Tr>
                      <Table.Th>Campaign</Table.Th>
                      <Table.Th>Status</Table.Th>
                      <Table.Th>Total</Table.Th>
                      <Table.Th>Completion</Table.Th>
                    </Table.Tr>
                  </Table.Thead>
                  <Table.Tbody>
                    {(campaigns.data?.rows || []).map((row) => {
                      const conversion = m.conversion_by_campaign?.[row.campaign_id];
                      const rate = Number(conversion?.rate || 0);
                      return (
                        <Table.Tr key={row.campaign_id}>
                          <Table.Td>{row.name || row.campaign_id}</Table.Td>
                          <Table.Td>
                            <Badge variant="light">{row.status}</Badge>
                          </Table.Td>
                          <Table.Td>{row.total_accounts}</Table.Td>
                          <Table.Td>
                            <Group gap="xs">
                              <Progress value={Math.min(100, Math.max(0, rate))} style={{ flex: 1 }} />
                              <Text size="sm">{percent(rate)}</Text>
                            </Group>
                          </Table.Td>
                        </Table.Tr>
                      );
                    })}
                  </Table.Tbody>
                </Table>
              </ScrollArea>
            ) : (
              <EmptyStateCard title="No campaigns yet" description="Create or launch a campaign to start showing queue health and campaign completion." />
            )}
          </Card>
        </Grid.Col>
      </Grid>
    </Stack>
  );
}
