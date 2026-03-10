import {
  ActionIcon,
  Badge,
  Button,
  Card,
  Collapse,
  Grid,
  Group,
  Loader,
  Menu,
  Paper,
  Progress,
  RingProgress,
  ScrollArea,
  Select,
  SimpleGrid,
  Stack,
  Table,
  Text,
  ThemeIcon,
  Title,
} from "@mantine/core";
import { useDisclosure } from "@mantine/hooks";
import { useQuery } from "@tanstack/react-query";
import {
  AlertTriangle,
  Brain,
  Calendar,
  ChevronDown,
  Clock,
  Download,
  FileSpreadsheet,
  Filter,
  Landmark,
  Layers,
  Phone,
  PhoneCall,
  RefreshCw,
  ShieldAlert,
  Target,
  TrendingDown,
  TrendingUp,
  UserCheck,
  Users,
  Wallet,
  Zap,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip as RechartsTooltip,
  XAxis,
  YAxis,
} from "recharts";

import { apiFetch, toQuery } from "../../api/client";
import { EmptyStateCard } from "../../components/EmptyStateCard";
import { ModuleHeader } from "../../components/ModuleHeader";
import type { ApiListResponse, BuildInfo, CampaignRow, SessionSnapshot, TaskRow } from "../../types/api";

const COLORS = {
  primary: "#125dff",
  primaryLight: "rgba(18, 93, 255, 0.12)",
  success: "#1f8f5a",
  successLight: "rgba(31, 143, 90, 0.12)",
  warning: "#b87820",
  warningLight: "rgba(184, 120, 32, 0.12)",
  danger: "#cd3f46",
  dangerLight: "rgba(205, 63, 70, 0.12)",
  info: "#1682d8",
  infoLight: "rgba(22, 130, 216, 0.12)",
  teal: "#0ab08b",
  tealLight: "rgba(10, 176, 139, 0.12)",
  purple: "#7c3aed",
  purpleLight: "rgba(124, 58, 237, 0.12)",
  slate: "#64748b",
  slateLight: "rgba(100, 116, 139, 0.12)",
};

const BUCKET_COLORS: Record<string, string> = {
  "1-30": "#22c55e",
  "31-60": "#eab308",
  "61-90": "#f97316",
  "90+": "#ef4444",
};

const STATE_COLORS: Record<string, string> = {
  NEW: COLORS.primary,
  IN_PROGRESS: COLORS.info,
  PTP: COLORS.success,
  CALLBACK: COLORS.warning,
  ESCALATED: COLORS.danger,
  CLOSED: COLORS.slate,
};

const CHART_THEME = {
  grid: "var(--te-command-chart-grid)",
  axisText: "var(--te-command-chart-axis)",
  axisLine: "var(--te-command-chart-axis-line)",
  tooltipBg: "var(--te-command-tooltip-bg)",
  tooltipBorder: "var(--te-command-tooltip-border)",
  tooltipShadow: "var(--te-command-tooltip-shadow)",
  tooltipText: "var(--te-command-tooltip-text)",
  subtleSurface: "var(--te-command-subtle-surface)",
  subtleBorder: "var(--te-command-subtle-border)",
  trackBg: "var(--te-command-track-bg)",
};

const CHART_AXIS_TICK = { fontSize: 12, fill: CHART_THEME.axisText };
const CHART_AXIS_TICK_SMALL = { fontSize: 11, fill: CHART_THEME.axisText };
const CHART_AXIS_LINE = { stroke: CHART_THEME.axisLine };
const CHART_TOOLTIP_STYLE = {
  background: CHART_THEME.tooltipBg,
  border: `1px solid ${CHART_THEME.tooltipBorder}`,
  borderRadius: 12,
  boxShadow: CHART_THEME.tooltipShadow,
  color: CHART_THEME.tooltipText,
};
const CHART_TOOLTIP_TEXT_STYLE = { color: CHART_THEME.tooltipText };
const CHART_SUBTLE_PANEL_STYLE = {
  background: CHART_THEME.subtleSurface,
  border: `1px solid ${CHART_THEME.subtleBorder}`,
};

const DATE_RANGE_OPTIONS = [
  { value: "today", label: "Today" },
  { value: "last_7", label: "Last 7 Days" },
  { value: "last_30", label: "Last 30 Days" },
  { value: "last_90", label: "Last 90 Days" },
];

const TASK_STATE_OPTIONS = [
  { value: "", label: "All task states" },
  { value: "NEW", label: "New" },
  { value: "IN_PROGRESS", label: "In Progress" },
  { value: "PTP", label: "PTP" },
  { value: "CALLBACK", label: "Callback" },
  { value: "ESCALATED", label: "Escalated" },
  { value: "CLOSED", label: "Closed" },
];

const DPD_BUCKET_OPTIONS = [
  { value: "", label: "All buckets" },
  { value: "1-30", label: "1-30 DPD" },
  { value: "31-60", label: "31-60 DPD" },
  { value: "61-90", label: "61-90 DPD" },
  { value: "90+", label: "90+ DPD" },
];

const TASK_STATE_ORDER = ["NEW", "IN_PROGRESS", "PTP", "CALLBACK", "ESCALATED", "CLOSED"] as const;
const LIVE_REFRESH_MS = 10_000;

interface MetricsResponse {
  sessions_today: number;
  ptp_count: number;
  callback_count: number;
  escalations: number;
  retries_pending: number;
  avg_handle_seconds?: number | null;
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
  profanity_incidents?: number;
  queue_snapshot?: Record<string, number>;
  bucket_heatmap?: Record<string, number>;
  ptp_rate_by_bucket?: Record<string, { total: number; ptp: number; rate: number }>;
}

interface RollForwardResponse {
  buckets: string[];
  matrix: Record<string, Record<string, number>>;
  total_transitions: number;
  roll_forward_count: number;
  roll_forward_pct: number;
  rollback_count?: number;
  rollback_pct?: number;
  cure_count?: number;
  cure_rate_pct?: number;
  window_days: number;
}

interface RecoveryResponse {
  dates: string[];
  amounts: number[];
  total_recovered: number;
  portfolio_value: number;
  recovery_rate_pct: number;
  window_days: number;
  reconciliation: Array<{ date?: string; session_id?: string; customer_id?: string; amount?: number }>;
}

interface AgentMetric {
  rank: number;
  agent_id?: string;
  display_name: string;
  total_calls: number;
  connect_rate_pct: number;
  avg_handle_time_s: number;
  ptp_count: number;
  ptp_conversion_pct: number;
  escalations: number;
  compliance_violations: number;
}

interface BucketMetric {
  bucket: string;
  exposure: number;
  share: number;
  ptpRate: number;
  ptpCount: number;
  ptpTotal: number;
  color: string;
}

interface SignalTileProps {
  title: string;
  value: string;
  detail: string;
  color: string;
  icon: React.ReactNode;
}

interface RecommendationTileProps {
  title: string;
  countLabel: string;
  detail: string;
  color: string;
  icon: React.ReactNode;
}

interface QueueAction {
  title: string;
  count: number;
  detail: string;
  color: string;
  icon: React.ReactNode;
}

interface KPICardProps {
  label: string;
  value: string | number;
  subValue?: string;
  trend?: number;
  icon?: React.ReactNode;
  color?: string;
}

interface SectionHeaderProps {
  title: string;
  subtitle?: string;
  icon: React.ReactNode;
  badge?: string;
  badgeColor?: string;
  action?: React.ReactNode;
}

function rupees(n: number): string {
  try {
    return new Intl.NumberFormat("en-IN", {
      style: "currency",
      currency: "INR",
      maximumFractionDigits: 0,
    }).format(n || 0);
  } catch {
    return `₹${Math.round(n || 0).toLocaleString("en-IN")}`;
  }
}

function rupeesCompact(n: number): string {
  if (n >= 10000000) return `₹${(n / 10000000).toFixed(1)}Cr`;
  if (n >= 100000) return `₹${(n / 100000).toFixed(1)}L`;
  if (n >= 1000) return `₹${(n / 1000).toFixed(1)}K`;
  return rupees(n);
}

function percent(n?: number | null): string {
  return `${Number(n || 0).toFixed(1)}%`;
}

function formatNumber(n: number): string {
  return new Intl.NumberFormat("en-IN").format(n || 0);
}

function formatDuration(seconds?: number | null): string {
  const totalSeconds = Math.max(0, Math.round(Number(seconds || 0)));
  const minutes = Math.floor(totalSeconds / 60);
  const remainder = totalSeconds % 60;
  if (minutes <= 0) {
    return `${remainder}s`;
  }
  return `${minutes}m ${remainder}s`;
}

function formatShortDate(value?: string): string {
  if (!value) {
    return "-";
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return parsed.toLocaleDateString("en-IN", { month: "short", day: "numeric" });
}

function stateLabel(state: string): string {
  return state.replaceAll("_", " ");
}

function daysFromRange(range: string): number {
  switch (range) {
    case "today":
      return 1;
    case "last_7":
      return 7;
    case "last_90":
      return 90;
    default:
      return 30;
  }
}

function clamp(value: number, min = 0, max = 100): number {
  return Math.min(max, Math.max(min, value));
}

function pressureLabel(score: number): { label: string; color: string; detail: string } {
  if (score >= 76) {
    return {
      label: "Intervention",
      color: "red",
      detail: "Queue pressure is high enough that collections leadership should intervene now.",
    };
  }
  if (score >= 56) {
    return {
      label: "Tight",
      color: "orange",
      detail: "The campaign is still recoverable, but rollover and follow-up exceptions are accumulating.",
    };
  }
  if (score >= 31) {
    return {
      label: "Watch",
      color: "blue",
      detail: "Current pressure is manageable, but the next movement window should be watched closely.",
    };
  }
  return {
    label: "Stable",
    color: "green",
    detail: "Current campaign behavior is within normal operating guardrails.",
  };
}

function KPICard({ label, value, subValue, trend, icon, color = COLORS.primary }: KPICardProps) {
  const TrendIcon = trend && trend > 0 ? TrendingUp : trend && trend < 0 ? TrendingDown : null;

  return (
    <Card className="te-command-kpi">
      <Group justify="space-between" align="flex-start" mb="xs">
        <Text size="xs" tt="uppercase" fw={700} c="dimmed" style={{ letterSpacing: "0.06em" }}>
          {label}
        </Text>
        {icon ? (
          <ThemeIcon size="sm" variant="light" color="blue" radius="md">
            {icon}
          </ThemeIcon>
        ) : null}
      </Group>
      <Title order={2} style={{ color, letterSpacing: "-0.02em" }}>
        {value}
      </Title>
      {subValue || trend !== undefined ? (
        <Group gap="xs" mt="xs">
          {trend !== undefined && TrendIcon ? (
            <Badge variant="light" color={trend > 0 ? "green" : "red"} size="sm" leftSection={<TrendIcon size={12} />}>
              {Math.abs(trend).toFixed(1)}%
            </Badge>
          ) : null}
          {subValue ? (
            <Text size="xs" c="dimmed">
              {subValue}
            </Text>
          ) : null}
        </Group>
      ) : null}
    </Card>
  );
}

function SectionHeader({ title, subtitle, icon, badge, badgeColor = "blue", action }: SectionHeaderProps) {
  return (
    <Group justify="space-between" align="flex-start" mb="md">
      <Group gap="sm">
        <ThemeIcon size="lg" variant="light" color="blue" radius="md">
          {icon}
        </ThemeIcon>
        <div>
          <Group gap="xs">
            <Title order={4} style={{ letterSpacing: "-0.01em" }}>
              {title}
            </Title>
            {badge ? (
              <Badge variant="light" color={badgeColor} size="sm">
                {badge}
              </Badge>
            ) : null}
          </Group>
          {subtitle ? (
            <Text size="sm" c="dimmed">
              {subtitle}
            </Text>
          ) : null}
        </div>
      </Group>
      {action}
    </Group>
  );
}

function SignalTile({ title, value, detail, color, icon }: SignalTileProps) {
  return (
    <Paper
      p="md"
      radius="md"
      style={{
        ...CHART_SUBTLE_PANEL_STYLE,
        background:
          color === COLORS.danger
            ? COLORS.dangerLight
            : color === COLORS.warning
            ? COLORS.warningLight
            : color === COLORS.success
            ? COLORS.successLight
            : color === COLORS.teal
            ? COLORS.tealLight
            : color === COLORS.purple
            ? COLORS.purpleLight
            : COLORS.primaryLight,
      }}
    >
      <Stack gap={8}>
        <Group justify="space-between" align="flex-start">
          <ThemeIcon radius="md" variant="light" color="blue">
            {icon}
          </ThemeIcon>
          <Badge variant="outline" color="gray">
            {title}
          </Badge>
        </Group>
        <Title order={3} style={{ color, letterSpacing: "-0.02em" }}>
          {value}
        </Title>
        <Text size="sm">{detail}</Text>
      </Stack>
    </Paper>
  );
}

function RecommendationTile({ title, countLabel, detail, color, icon }: RecommendationTileProps) {
  return (
    <Paper
      p="md"
      radius="md"
      style={{
        ...CHART_SUBTLE_PANEL_STYLE,
        background:
          color === COLORS.danger
            ? COLORS.dangerLight
            : color === COLORS.warning
            ? COLORS.warningLight
            : color === COLORS.success
            ? COLORS.successLight
            : color === COLORS.teal
            ? COLORS.tealLight
            : COLORS.primaryLight,
      }}
    >
      <Group justify="space-between" align="flex-start">
        <Group gap="sm" align="flex-start">
          <ThemeIcon radius="md" variant="light" color="blue">
            {icon}
          </ThemeIcon>
          <div>
            <Text size="sm" fw={600}>
              {title}
            </Text>
            <Text size="xs" c="dimmed" mt={4}>
              {detail}
            </Text>
          </div>
        </Group>
        <Badge variant="filled" color={color === COLORS.warning ? "orange" : color === COLORS.danger ? "red" : color === COLORS.success ? "green" : "blue"}>
          {countLabel}
        </Badge>
      </Group>
    </Paper>
  );
}

function GlobalFilters({
  dateRange,
  setDateRange,
  campaignId,
  setCampaignId,
  campaignOptions,
  taskState,
  setTaskState,
  bucket,
  setBucket,
}: {
  dateRange: string;
  setDateRange: (value: string) => void;
  campaignId: string;
  setCampaignId: (value: string) => void;
  campaignOptions: Array<{ value: string; label: string }>;
  taskState: string;
  setTaskState: (value: string) => void;
  bucket: string;
  setBucket: (value: string) => void;
}) {
  const [filtersOpen, { toggle: toggleFilters }] = useDisclosure(true);

  return (
    <Paper className="te-command-filter-bar" p="md" radius="lg" withBorder>
      <Group justify="space-between" mb={filtersOpen ? "md" : 0}>
        <Group gap="sm">
          <ThemeIcon size="md" variant="light" color="blue" radius="md">
            <Filter size={16} />
          </ThemeIcon>
          <div>
            <Text size="sm" fw={600}>
              Global Filters
            </Text>
            <Text size="xs" c="dimmed">
              Scope the command center to a live campaign and its current queue.
            </Text>
          </div>
        </Group>
        <Group gap="xs">
          <Button
            variant="subtle"
            size="xs"
            leftSection={<RefreshCw size={14} />}
            onClick={() => {
              setDateRange("last_30");
              setTaskState("");
              setBucket("");
            }}
          >
            Reset
          </Button>
          <ActionIcon variant="subtle" onClick={toggleFilters}>
            <ChevronDown
              size={18}
              style={{
                transform: filtersOpen ? "rotate(180deg)" : "rotate(0deg)",
                transition: "transform 200ms ease",
              }}
            />
          </ActionIcon>
        </Group>
      </Group>

      <Collapse in={filtersOpen}>
        <SimpleGrid cols={{ base: 1, sm: 2, md: 4 }} spacing="md">
          <Select
            label="Date Range"
            placeholder="Select period"
            value={dateRange}
            onChange={(value) => setDateRange(value || "last_30")}
            data={DATE_RANGE_OPTIONS}
            leftSection={<Calendar size={16} />}
          />
          <Select
            label="Campaign"
            placeholder="Select campaign"
            value={campaignId}
            onChange={(value) => setCampaignId(value || "")}
            data={campaignOptions}
            leftSection={<Landmark size={16} />}
            searchable
          />
          <Select
            label="Task State"
            placeholder="All task states"
            value={taskState}
            onChange={(value) => setTaskState(value || "")}
            data={TASK_STATE_OPTIONS}
            leftSection={<Target size={16} />}
          />
          <Select
            label="Delinquency Bucket"
            placeholder="All buckets"
            value={bucket}
            onChange={(value) => setBucket(value || "")}
            data={DPD_BUCKET_OPTIONS}
            leftSection={<Wallet size={16} />}
          />
        </SimpleGrid>
      </Collapse>
    </Paper>
  );
}

function PortfolioHealthSection({
  metrics,
  recovery,
  queueRows,
  selectedCampaign,
}: {
  metrics: MetricsResponse;
  recovery: RecoveryResponse;
  queueRows: Array<{ state: string; count: number; color: string }>;
  selectedCampaign: CampaignRow;
}) {
  const totalRecovered = Number(recovery.total_recovered || 0);
  const expectedRecovery = Number(metrics.expected_recovery_amount || 0);
  const recoveryGap = Math.max(0, expectedRecovery - totalRecovered);
  const recoveryData = (recovery.dates || []).map((date, index) => ({
    date: formatShortDate(date),
    amount: Number(recovery.amounts?.[index] || 0),
  }));

  return (
    <Card className="te-command-section">
      <SectionHeader
        title="Portfolio Health Overview"
        subtitle="Live campaign scope, recovery throughput, and queue posture"
        icon={<Landmark size={20} />}
        badge={selectedCampaign.status || "active"}
        badgeColor="green"
        action={
          <Badge variant="outline" color="blue">
            {formatNumber(Number(selectedCampaign.total_accounts || 0))} accounts
          </Badge>
        }
      />

      <SimpleGrid cols={{ base: 2, sm: 3, lg: 6 }} spacing="md" mb="lg">
        <KPICard
          label="Accounts In Scope"
          value={formatNumber(Number(metrics.accounts_assigned || selectedCampaign.total_accounts || 0))}
          subValue="Campaign queue"
          icon={<Users size={14} />}
        />
        <KPICard
          label="Accounts Contacted"
          value={formatNumber(Number(metrics.accounts_contacted || 0))}
          subValue="Distinct borrowers reached"
          icon={<UserCheck size={14} />}
          color={COLORS.info}
        />
        <KPICard
          label="Contact Coverage"
          value={percent(metrics.contact_rate_pct)}
          subValue="Reached vs assigned"
          icon={<Phone size={14} />}
          color={COLORS.success}
        />
        <KPICard
          label="Expected Recovery"
          value={rupeesCompact(expectedRecovery)}
          subValue="Current PTP book"
          icon={<Wallet size={14} />}
          color={COLORS.teal}
        />
        <KPICard
          label="Realized Recovery"
          value={rupeesCompact(totalRecovered)}
          subValue={`${percent(recovery.recovery_rate_pct)} realized`}
          icon={<TrendingUp size={14} />}
          color={COLORS.success}
        />
        <KPICard
          label="Recovery Gap"
          value={rupeesCompact(recoveryGap)}
          subValue={recoveryGap > 0 ? "Gap between expected and realized" : "Expected book is realized"}
          icon={<AlertTriangle size={14} />}
          color={recoveryGap > 0 ? COLORS.warning : COLORS.success}
        />
      </SimpleGrid>

      <Grid>
        <Grid.Col span={{ base: 12, lg: 7 }}>
          <Card className="te-command-chart-card">
            <Group justify="space-between" mb="md">
              <div>
                <Text size="sm" fw={600}>
                  Realized Recovery Trend
                </Text>
                <Text size="xs" c="dimmed">
                  Successful payment captures in the selected observation window
                </Text>
              </div>
              <Badge variant="light" size="sm">
                {recovery.window_days || 30} days
              </Badge>
            </Group>
            {recoveryData.length ? (
              <div style={{ height: 250 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={recoveryData}>
                    <defs>
                      <linearGradient id="te-command-recovery-fill" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor={COLORS.primary} stopOpacity={0.36} />
                        <stop offset="95%" stopColor={COLORS.primary} stopOpacity={0.04} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke={CHART_THEME.grid} />
                    <XAxis dataKey="date" tick={CHART_AXIS_TICK} axisLine={CHART_AXIS_LINE} tickLine={CHART_AXIS_LINE} />
                    <YAxis tick={CHART_AXIS_TICK} axisLine={CHART_AXIS_LINE} tickLine={CHART_AXIS_LINE} />
                    <RechartsTooltip
                      contentStyle={CHART_TOOLTIP_STYLE}
                      labelStyle={CHART_TOOLTIP_TEXT_STYLE}
                      itemStyle={CHART_TOOLTIP_TEXT_STYLE}
                      formatter={(value) => [rupees(Number(value || 0)), "Recovered"]}
                    />
                    <Area type="monotone" dataKey="amount" stroke={COLORS.primary} fill="url(#te-command-recovery-fill)" strokeWidth={2.5} />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            ) : (
              <EmptyStateCard
                title="No realized recovery yet"
                description="Successful payment captures will populate the campaign recovery trend here."
              />
            )}
          </Card>
        </Grid.Col>

        <Grid.Col span={{ base: 12, lg: 5 }}>
          <Card className="te-command-chart-card">
            <Group justify="space-between" mb="md">
              <div>
                <Text size="sm" fw={600}>
                  Queue Posture
                </Text>
                <Text size="xs" c="dimmed">
                  How the campaign is distributed across work states right now
                </Text>
              </div>
              <Badge variant="light" size="sm">
                Live
              </Badge>
            </Group>
            <Stack gap="sm">
              {queueRows.map((item) => {
                const maxCount = Math.max(1, ...queueRows.map((row) => row.count));
                return (
                  <div key={item.state}>
                    <Group justify="space-between" mb={6}>
                      <Text size="sm" fw={500}>
                        {stateLabel(item.state)}
                      </Text>
                      <Text size="sm" fw={700}>
                        {formatNumber(item.count)}
                      </Text>
                    </Group>
                    <Progress value={(item.count / maxCount) * 100} color={item.color} size="sm" radius="xl" />
                  </div>
                );
              })}
              <Paper p="md" radius="md" style={CHART_SUBTLE_PANEL_STYLE}>
                <Text size="xs" tt="uppercase" fw={700} c="dimmed">
                  Campaign scope
                </Text>
                <Title order={4} mt={6}>
                  {selectedCampaign.name || selectedCampaign.campaign_id}
                </Title>
                <Text size="sm" c="dimmed" mt={4}>
                  {selectedCampaign.campaign_id}
                </Text>
              </Paper>
            </Stack>
          </Card>
        </Grid.Col>
      </Grid>
    </Card>
  );
}

function DelinquencyRiskSection({
  bucketRows,
  rollForward,
}: {
  bucketRows: BucketMetric[];
  rollForward: RollForwardResponse;
}) {
  const totalExposure = bucketRows.reduce((sum, item) => sum + item.exposure, 0);
  const highRiskExposure = bucketRows
    .filter((item) => item.bucket === "61-90" || item.bucket === "90+")
    .reduce((sum, item) => sum + item.exposure, 0);
  const dominantBucket =
    bucketRows
      .slice()
      .sort((left, right) => right.exposure - left.exposure)[0] ||
    bucketRows[0];
  const containmentRate = rollForward.total_transitions > 0 ? 100 - Number(rollForward.roll_forward_pct || 0) : 0;

  return (
    <Card className="te-command-section">
      <SectionHeader
        title="Delinquency & Risk Intelligence"
        subtitle="Actual bucket concentration, movement risk, and commitment quality"
        icon={<ShieldAlert size={20} />}
        badge="Campaign live"
        badgeColor="orange"
      />

      <SimpleGrid cols={{ base: 2, sm: 4 }} spacing="md" mb="lg">
        <KPICard
          label="Total Exposure"
          value={formatNumber(totalExposure)}
          subValue="Accounts across DPD buckets"
          icon={<Layers size={14} />}
        />
        <KPICard
          label="Dominant Bucket"
          value={dominantBucket?.bucket || "-"}
          subValue={dominantBucket ? `${dominantBucket.share.toFixed(1)}% of campaign exposure` : "No exposure recorded"}
          icon={<AlertTriangle size={14} />}
          color={dominantBucket?.color || COLORS.slate}
        />
        <KPICard
          label="High-Risk Exposure"
          value={formatNumber(highRiskExposure)}
          subValue="61-90 and 90+ buckets"
          icon={<TrendingDown size={14} />}
          color={COLORS.warning}
        />
        <KPICard
          label="Containment Rate"
          value={rollForward.total_transitions ? percent(containmentRate) : "n/a"}
          subValue={rollForward.total_transitions ? `${rollForward.roll_forward_count} roll-forwards in window` : "Needs DPD history"}
          icon={<Target size={14} />}
          color={containmentRate >= 70 ? COLORS.success : COLORS.warning}
        />
      </SimpleGrid>

      <Grid>
        <Grid.Col span={{ base: 12, lg: 5 }}>
          <Card className="te-command-chart-card">
            <Group justify="space-between" mb="md">
              <Text size="sm" fw={600}>
                Bucket Exposure
              </Text>
              <Badge variant="light" size="sm">
                Accounts
              </Badge>
            </Group>
            <div style={{ height: 240 }}>
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={bucketRows}>
                  <CartesianGrid strokeDasharray="3 3" stroke={CHART_THEME.grid} />
                  <XAxis dataKey="bucket" tick={CHART_AXIS_TICK} axisLine={CHART_AXIS_LINE} tickLine={CHART_AXIS_LINE} />
                  <YAxis tick={CHART_AXIS_TICK} axisLine={CHART_AXIS_LINE} tickLine={CHART_AXIS_LINE} />
                  <RechartsTooltip
                    contentStyle={CHART_TOOLTIP_STYLE}
                    labelStyle={CHART_TOOLTIP_TEXT_STYLE}
                    itemStyle={CHART_TOOLTIP_TEXT_STYLE}
                    formatter={(value) => [formatNumber(Number(value || 0)), "Accounts"]}
                  />
                  <Bar dataKey="exposure" radius={[4, 4, 0, 0]}>
                    {bucketRows.map((entry) => (
                      <Cell key={entry.bucket} fill={entry.color} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </Card>
        </Grid.Col>

        <Grid.Col span={{ base: 12, lg: 7 }}>
          <Card className="te-command-chart-card">
            <Group justify="space-between" mb="md">
              <Text size="sm" fw={600}>
                PTP Quality by Bucket
              </Text>
              <Badge variant="light" size="sm">
                Actual commitments
              </Badge>
            </Group>
            <Stack gap="md">
              {bucketRows.map((item) => (
                <div key={item.bucket}>
                  <Group justify="space-between" mb="xs">
                    <div>
                      <Text size="sm" fw={500}>
                        {item.bucket} DPD
                      </Text>
                      <Text size="xs" c="dimmed">
                        {formatNumber(item.ptpCount)} commitments from {formatNumber(item.ptpTotal)} observed outcomes
                      </Text>
                    </div>
                    <Text size="sm" fw={700} style={{ color: item.color }}>
                      {percent(item.ptpRate)}
                    </Text>
                  </Group>
                  <Progress value={clamp(item.ptpRate)} color={item.color} radius="xl" size="md" />
                </div>
              ))}
            </Stack>
          </Card>
        </Grid.Col>

        <Grid.Col span={12}>
          <Card className="te-command-chart-card">
            <Group justify="space-between" mb="md">
              <Text size="sm" fw={600}>
                Roll Rate Matrix
              </Text>
              <Badge variant="light" size="sm">
                {rollForward.window_days || 30} day transitions
              </Badge>
            </Group>
            {rollForward.total_transitions ? (
              <ScrollArea>
                <Table className="te-command-matrix-table">
                  <Table.Thead>
                    <Table.Tr>
                      <Table.Th>From / To</Table.Th>
                      {rollForward.buckets.map((bucket) => (
                        <Table.Th key={bucket}>{bucket}</Table.Th>
                      ))}
                    </Table.Tr>
                  </Table.Thead>
                  <Table.Tbody>
                    {rollForward.buckets.map((fromBucket) => (
                      <Table.Tr key={fromBucket}>
                        <Table.Td fw={600}>{fromBucket}</Table.Td>
                        {rollForward.buckets.map((toBucket) => {
                          const value = Number(rollForward.matrix?.[fromBucket]?.[toBucket] || 0);
                          const alpha = value > 0 ? Math.min(0.42, 0.08 + value / Math.max(1, rollForward.total_transitions)) : 0;
                          const baseColor =
                            toBucket === "0"
                              ? "34, 197, 94"
                              : toBucket === "1-30"
                              ? "59, 130, 246"
                              : toBucket === "31-60"
                              ? "234, 179, 8"
                              : toBucket === "61-90"
                              ? "249, 115, 22"
                              : "239, 68, 68";
                          return (
                            <Table.Td
                              key={`${fromBucket}-${toBucket}`}
                              style={{
                                background: `rgba(${baseColor}, ${alpha})`,
                              }}
                            >
                              {formatNumber(value)}
                            </Table.Td>
                          );
                        })}
                      </Table.Tr>
                    ))}
                  </Table.Tbody>
                </Table>
              </ScrollArea>
            ) : (
              <EmptyStateCard
                title="No DPD transition history yet"
                description="Run the campaign long enough to accumulate DPD snapshots and the roll-rate matrix will populate here."
              />
            )}
          </Card>
        </Grid.Col>
      </Grid>
    </Card>
  );
}

function RecoveryPerformanceSection({
  metrics,
  recovery,
  agents,
}: {
  metrics: MetricsResponse;
  recovery: RecoveryResponse;
  agents: AgentMetric[];
}) {
  const totalRecovered = Number(recovery.total_recovered || 0);
  const expectedRecovery = Number(metrics.expected_recovery_amount || 0);
  const paymentsCaptured = recovery.reconciliation.length;
  const funnelData = [
    { label: "Assigned", value: Number(metrics.accounts_assigned || 0), color: COLORS.primary },
    { label: "Contacted", value: Number(metrics.accounts_contacted || 0), color: COLORS.info },
    { label: "PTP Captured", value: Number(metrics.ptp_count || 0), color: COLORS.teal },
    { label: "Callbacks", value: Number(metrics.callback_count || 0), color: COLORS.warning },
    { label: "Payments", value: paymentsCaptured, color: COLORS.success },
  ];
  const topAgents = agents.slice(0, 5);
  const recoveryProgress = expectedRecovery > 0 ? clamp((totalRecovered / expectedRecovery) * 100) : 0;
  const followupDiscipline = clamp(Number(metrics.followup_discipline_rate_pct || 0));
  const followupGap = Math.max(0, Number(metrics.followups_due_today || 0) - Number(metrics.followups_completed_today || 0));

  return (
    <Card className="te-command-section">
      <SectionHeader
        title="Recovery Performance"
        subtitle="Commitments, cash realization, and recovery conversion grounded in live campaign activity"
        icon={<Target size={20} />}
        badge="Performance"
        badgeColor="green"
      />

      <SimpleGrid cols={{ base: 2, sm: 3, lg: 6 }} spacing="md" mb="lg">
        <KPICard
          label="Recovery Rate"
          value={percent(recovery.recovery_rate_pct)}
          subValue="Recovered vs portfolio value"
          icon={<TrendingUp size={14} />}
          color={COLORS.success}
        />
        <KPICard
          label="Recovered"
          value={rupeesCompact(totalRecovered)}
          subValue="Captured payments"
          icon={<Wallet size={14} />}
          color={COLORS.success}
        />
        <KPICard
          label="Expected Recovery"
          value={rupeesCompact(expectedRecovery)}
          subValue="Open committed book"
          icon={<PhoneCall size={14} />}
          color={COLORS.teal}
        />
        <KPICard
          label="PTP Captured"
          value={formatNumber(Number(metrics.ptp_count || 0))}
          subValue="Actual commitment count"
          icon={<UserCheck size={14} />}
          color={COLORS.primary}
        />
        <KPICard
          label="Callbacks Logged"
          value={formatNumber(Number(metrics.callback_count || 0))}
          subValue={`${followupGap} still due today`}
          icon={<Clock size={14} />}
          color={followupGap > 0 ? COLORS.warning : COLORS.info}
        />
        <KPICard
          label="Follow-up Discipline"
          value={percent(metrics.followup_discipline_rate_pct)}
          subValue={`${formatNumber(Number(metrics.followups_completed_today || 0))}/${formatNumber(Number(metrics.followups_due_today || 0))} done today`}
          icon={<Target size={14} />}
          color={followupDiscipline >= 80 ? COLORS.success : COLORS.warning}
        />
      </SimpleGrid>

      <Grid>
        <Grid.Col span={{ base: 12, lg: 5 }}>
          <Card className="te-command-chart-card">
            <Group justify="space-between" mb="md">
              <Text size="sm" fw={600}>
                Commitment to Cash Funnel
              </Text>
              <Badge variant="light" size="sm">
                Campaign actuals
              </Badge>
            </Group>
            <Stack gap="sm">
              {funnelData.map((item, index) => {
                const maxValue = Math.max(1, funnelData[0]?.value || 1);
                const width = (item.value / maxValue) * 100;
                const conversion =
                  index > 0 && funnelData[index - 1].value > 0
                    ? ((item.value / funnelData[index - 1].value) * 100).toFixed(1)
                    : "100.0";
                return (
                  <div key={item.label}>
                    <Group justify="space-between" mb={6}>
                      <Text size="sm" fw={500}>
                        {item.label}
                      </Text>
                      <Group gap="xs">
                        <Text size="sm" fw={600}>
                          {formatNumber(item.value)}
                        </Text>
                        {index > 0 ? (
                          <Badge size="xs" variant="light" color="blue">
                            {conversion}%
                          </Badge>
                        ) : null}
                      </Group>
                    </Group>
                    <div
                      style={{
                        height: 28,
                        background: CHART_THEME.trackBg,
                        border: `1px solid ${CHART_THEME.subtleBorder}`,
                        borderRadius: 8,
                        overflow: "hidden",
                      }}
                    >
                      <div
                        style={{
                          width: `${width}%`,
                          height: "100%",
                          background: item.color,
                          borderRadius: 8,
                        }}
                      />
                    </div>
                  </div>
                );
              })}
            </Stack>
          </Card>
        </Grid.Col>

        <Grid.Col span={{ base: 12, lg: 7 }}>
          <Card className="te-command-chart-card">
            <Group justify="space-between" mb="md">
              <Text size="sm" fw={600}>
                Agent Recovery Conversion
              </Text>
              <Badge variant="light" size="sm">
                PTP + connect quality
              </Badge>
            </Group>
            {topAgents.length ? (
              <Grid>
                <Grid.Col span={{ base: 12, md: 5 }}>
                  <Stack align="center" justify="center" h="100%">
                    <RingProgress
                      size={160}
                      thickness={16}
                      roundCaps
                      sections={[
                        { value: recoveryProgress, color: COLORS.success },
                        { value: Math.max(0, 100 - recoveryProgress), color: "rgba(100, 116, 139, 0.18)" },
                      ]}
                      label={
                        <div style={{ textAlign: "center" }}>
                          <Text size="xs" c="dimmed">
                            Recovery vs expected
                          </Text>
                          <Title order={3}>{recoveryProgress.toFixed(0)}%</Title>
                        </div>
                      }
                    />
                    <Text size="sm" c="dimmed" ta="center">
                      {rupeesCompact(totalRecovered)} recovered against {rupeesCompact(expectedRecovery)} expected.
                    </Text>
                  </Stack>
                </Grid.Col>
                <Grid.Col span={{ base: 12, md: 7 }}>
                  <Stack gap="sm">
                    {topAgents.map((agent) => (
                      <Paper key={agent.display_name} p="sm" radius="md" style={CHART_SUBTLE_PANEL_STYLE}>
                        <Group justify="space-between" align="center">
                          <div>
                            <Text size="sm" fw={600}>
                              {agent.display_name}
                            </Text>
                            <Text size="xs" c="dimmed">
                              {formatNumber(agent.total_calls)} calls, {formatDuration(agent.avg_handle_time_s)} average handle time
                            </Text>
                          </div>
                          <Group gap="sm">
                            <Badge variant="light" color="green">
                              {percent(agent.ptp_conversion_pct)} PTP
                            </Badge>
                            <Badge variant="outline" color="blue">
                              {percent(agent.connect_rate_pct)} connect
                            </Badge>
                          </Group>
                        </Group>
                      </Paper>
                    ))}
                  </Stack>
                </Grid.Col>
              </Grid>
            ) : (
              <EmptyStateCard
                title="No agent recovery history yet"
                description="Once voice or manual commitments are logged, the recovery conversion view will populate here."
              />
            )}
          </Card>
        </Grid.Col>
      </Grid>
    </Card>
  );
}

function CollectionsOperationsSection({
  metrics,
  queueRows,
  agents,
  sessions,
}: {
  metrics: MetricsResponse;
  queueRows: Array<{ state: string; count: number; color: string }>;
  agents: AgentMetric[];
  sessions: SessionSnapshot[];
}) {
  const activeQueue = queueRows
    .filter((item) => item.state !== "CLOSED")
    .reduce((sum, item) => sum + item.count, 0);

  return (
    <Card className="te-command-section">
      <SectionHeader
        title="Collections Operations Monitoring"
        subtitle="Queue control, live calling activity, and operator performance"
        icon={<PhoneCall size={20} />}
        badge="Operations"
        badgeColor="blue"
      />

      <SimpleGrid cols={{ base: 2, sm: 4 }} spacing="md" mb="lg">
        <KPICard
          label="Active Queue"
          value={formatNumber(activeQueue)}
          subValue="Open work items"
          icon={<Layers size={14} />}
        />
        <KPICard
          label="Live Sessions"
          value={formatNumber(sessions.length)}
          subValue="Current websocket session snapshots"
          icon={<Phone size={14} />}
          color={sessions.length ? COLORS.success : COLORS.slate}
        />
        <KPICard
          label="Escalations"
          value={formatNumber(Number(metrics.escalations || 0))}
          subValue="Campaign total"
          icon={<AlertTriangle size={14} />}
          color={Number(metrics.escalations || 0) > 0 ? COLORS.warning : COLORS.success}
        />
        <KPICard
          label="SLA Breaches"
          value={formatNumber(Number(metrics.sla_breaches || 0))}
          subValue="Open overdue task breaches"
          icon={<Clock size={14} />}
          color={Number(metrics.sla_breaches || 0) > 0 ? COLORS.danger : COLORS.success}
        />
      </SimpleGrid>

      <Grid>
        <Grid.Col span={{ base: 12, lg: 5 }}>
          <Card className="te-command-chart-card">
            <Group justify="space-between" mb="md">
              <Text size="sm" fw={600}>
                Queue by Task State
              </Text>
              <Badge variant="light" size="sm">
                Live queue
              </Badge>
            </Group>
            <div style={{ height: 250 }}>
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={queueRows}>
                  <CartesianGrid strokeDasharray="3 3" stroke={CHART_THEME.grid} />
                  <XAxis dataKey="state" tick={CHART_AXIS_TICK_SMALL} axisLine={CHART_AXIS_LINE} tickLine={CHART_AXIS_LINE} />
                  <YAxis tick={CHART_AXIS_TICK} axisLine={CHART_AXIS_LINE} tickLine={CHART_AXIS_LINE} />
                  <RechartsTooltip
                    contentStyle={CHART_TOOLTIP_STYLE}
                    labelStyle={CHART_TOOLTIP_TEXT_STYLE}
                    itemStyle={CHART_TOOLTIP_TEXT_STYLE}
                    formatter={(value) => [formatNumber(Number(value || 0)), "Tasks"]}
                  />
                  <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                    {queueRows.map((row) => (
                      <Cell key={row.state} fill={row.color} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </Card>
        </Grid.Col>

        <Grid.Col span={{ base: 12, lg: 7 }}>
          <Card className="te-command-chart-card">
            <Group justify="space-between" mb="md">
              <Text size="sm" fw={600}>
                Live Session Monitor
              </Text>
              <Badge variant="light" size="sm">
                {sessions.length} active
              </Badge>
            </Group>
            {sessions.length ? (
              <Stack gap="sm">
                {sessions.slice(0, 6).map((session) => (
                  <Paper key={session.session_id} p="sm" radius="md" style={CHART_SUBTLE_PANEL_STYLE}>
                    <Group justify="space-between" align="flex-start">
                      <div>
                        <Text size="sm" fw={600}>
                          {session.customer_name || session.customer_id || "Unidentified borrower"}
                        </Text>
                        <Text size="xs" c="dimmed">
                          {session.session_id}
                        </Text>
                      </div>
                      <Group gap="xs">
                        {session.dpd_bucket ? (
                          <Badge variant="light" color="blue">
                            {session.dpd_bucket}
                          </Badge>
                        ) : null}
                        {session.step || session.current_step ? (
                          <Badge variant="outline" color="gray">
                            {session.current_step || session.step}
                          </Badge>
                        ) : null}
                      </Group>
                    </Group>
                    <Group gap="lg" mt="sm">
                      <Text size="xs" c="dimmed">
                        Phone: {session.phone || "-"}
                      </Text>
                      <Text size="xs" c="dimmed">
                        Due: {rupees(Number(session.amount_due || session.due_amount || 0))}
                      </Text>
                      <Text size="xs" c="dimmed">
                        Disposition: {session.disposition || "live"}
                      </Text>
                    </Group>
                  </Paper>
                ))}
              </Stack>
            ) : (
              <EmptyStateCard
                title="No live session snapshots"
                description="Once the selected campaign is being worked in the calling desk, active sessions will appear here."
              />
            )}
          </Card>
        </Grid.Col>

        <Grid.Col span={12}>
          <Card className="te-command-chart-card">
            <Group justify="space-between" mb="md">
              <Text size="sm" fw={600}>
                Agent Leaderboard
              </Text>
              <Badge variant="light" size="sm">
                Current campaign
              </Badge>
            </Group>
            {agents.length ? (
              <ScrollArea>
                <Table>
                  <Table.Thead>
                    <Table.Tr>
                      <Table.Th>Agent</Table.Th>
                      <Table.Th>Calls</Table.Th>
                      <Table.Th>Connect</Table.Th>
                      <Table.Th>PTP</Table.Th>
                      <Table.Th>Escalations</Table.Th>
                      <Table.Th>Compliance</Table.Th>
                    </Table.Tr>
                  </Table.Thead>
                  <Table.Tbody>
                    {agents.slice(0, 6).map((agent) => (
                      <Table.Tr key={agent.agent_id || agent.display_name}>
                        <Table.Td>
                          <Text fw={600}>{agent.display_name}</Text>
                        </Table.Td>
                        <Table.Td>{formatNumber(agent.total_calls)}</Table.Td>
                        <Table.Td>{percent(agent.connect_rate_pct)}</Table.Td>
                        <Table.Td>{percent(agent.ptp_conversion_pct)}</Table.Td>
                        <Table.Td>{formatNumber(agent.escalations)}</Table.Td>
                        <Table.Td>
                          <Badge variant="light" color={agent.compliance_violations > 0 ? "red" : "green"}>
                            {agent.compliance_violations > 0 ? `${agent.compliance_violations} issues` : "Clean"}
                          </Badge>
                        </Table.Td>
                      </Table.Tr>
                    ))}
                  </Table.Tbody>
                </Table>
              </ScrollArea>
            ) : (
              <EmptyStateCard
                title="No agent metrics yet"
                description="Once agents start working this campaign, the leaderboard will show connect, PTP, and compliance performance."
              />
            )}
          </Card>
        </Grid.Col>
      </Grid>
    </Card>
  );
}

function AIDecisionIntelligenceSection({
  bucketRows,
  metrics,
  recovery,
  rollForward,
  agents,
  recommendations,
}: {
  bucketRows: BucketMetric[];
  metrics: MetricsResponse;
  recovery: RecoveryResponse;
  rollForward: RollForwardResponse;
  agents: AgentMetric[];
  recommendations: RecommendationTileProps[];
}) {
  const dominantBucket =
    bucketRows
      .slice()
      .sort((left, right) => right.exposure - left.exposure)[0] ||
    bucketRows[0];
  const weakestBucket =
    bucketRows
      .slice()
      .filter((item) => item.exposure > 0 || item.ptpTotal > 0)
      .sort((left, right) => left.ptpRate - right.ptpRate || right.exposure - left.exposure)[0] ||
    dominantBucket;
  const recoveryGap = Math.max(0, Number(metrics.expected_recovery_amount || 0) - Number(recovery.total_recovered || 0));
  const pressureScore = Math.round(
    clamp(
      Number(rollForward.roll_forward_pct || 0) * 1.8 +
        Math.max(0, 75 - Number(metrics.followup_discipline_rate_pct || 0)) +
        Math.min(20, Number(metrics.sla_breaches || 0) * 4) +
        Math.min(18, Number(metrics.retries_pending || 0) * 3) +
        Math.min(16, Number(metrics.ptp_miss_open_alerts || 0) * 4),
    ),
  );
  const pressure = pressureLabel(pressureScore);
  const bestOperator =
    agents
      .slice()
      .sort((left, right) => right.ptp_conversion_pct - left.ptp_conversion_pct || right.total_calls - left.total_calls)[0] || null;
  const signalTiles: SignalTileProps[] = [
    {
      title: "Dominant exposure",
      value: dominantBucket ? `${dominantBucket.bucket} DPD` : "No exposure",
      detail: dominantBucket
        ? `${formatNumber(dominantBucket.exposure)} accounts, ${dominantBucket.share.toFixed(1)}% of current delinquent exposure.`
        : "No live bucket pressure is available yet.",
      color: dominantBucket?.color || COLORS.slate,
      icon: <Layers size={16} />,
    },
    {
      title: "Weakest commitment lane",
      value: weakestBucket ? percent(weakestBucket.ptpRate) : "n/a",
      detail: weakestBucket
        ? `${weakestBucket.bucket} DPD is converting commitments least effectively right now.`
        : "No commitment history is available yet.",
      color: weakestBucket?.color || COLORS.slate,
      icon: <TrendingDown size={16} />,
    },
    {
      title: "Operating pressure",
      value: `${pressureScore}/100`,
      detail: pressure.detail,
      color: pressure.color === "red" ? COLORS.danger : pressure.color === "orange" ? COLORS.warning : pressure.color === "green" ? COLORS.success : COLORS.primary,
      icon: <Brain size={16} />,
    },
    {
      title: "Recovery gap",
      value: rupeesCompact(recoveryGap),
      detail: recoveryGap > 0 ? "Expected commitments still exceed realized payments." : "Realized payments are in line with the current commitment book.",
      color: recoveryGap > 0 ? COLORS.warning : COLORS.success,
      icon: <Target size={16} />,
    },
  ];

  return (
    <Card className="te-command-section">
      <SectionHeader
        title="AI Decision Intelligence"
        subtitle="Recommendations derived from the actual campaign, queue, and recovery signals"
        icon={<Brain size={20} />}
        badge={pressure.label}
        badgeColor={pressure.color}
      />

      <Grid>
        <Grid.Col span={{ base: 12, lg: 5 }}>
          <Card className="te-command-chart-card">
            <Group justify="space-between" mb="md">
              <Text size="sm" fw={600}>
                Decision Signals
              </Text>
              <Badge variant="light" color="violet" size="sm">
                Derived from live metrics
              </Badge>
            </Group>
            <Stack gap="sm">
              {signalTiles.map((item) => (
                <SignalTile key={item.title} {...item} />
              ))}
            </Stack>
          </Card>
        </Grid.Col>

        <Grid.Col span={{ base: 12, lg: 7 }}>
          <Card className="te-command-chart-card">
            <Group justify="space-between" mb="md">
              <Text size="sm" fw={600}>
                Recommended Actions
              </Text>
              <Badge variant="light" color="violet" size="sm">
                Real queue drivers
              </Badge>
            </Group>
            <Stack gap="sm">
              {recommendations.map((item) => (
                <RecommendationTile key={item.title} {...item} />
              ))}
            </Stack>
            <SimpleGrid cols={{ base: 1, sm: 2 }} mt="md">
              <Paper p="md" radius="md" style={CHART_SUBTLE_PANEL_STYLE}>
                <Text size="xs" tt="uppercase" fw={700} c="dimmed">
                  Pressure posture
                </Text>
                <Title order={3} mt={8}>
                  {pressure.label}
                </Title>
                <Text size="sm" c="dimmed" mt={4}>
                  Roll-forward, missed follow-up, and breach counts are combined into a single operating pressure score.
                </Text>
              </Paper>
              <Paper p="md" radius="md" style={CHART_SUBTLE_PANEL_STYLE}>
                <Text size="xs" tt="uppercase" fw={700} c="dimmed">
                  Best operator
                </Text>
                <Title order={3} mt={8}>
                  {bestOperator?.display_name || "No signal yet"}
                </Title>
                <Text size="sm" c="dimmed" mt={4}>
                  {bestOperator
                    ? `${percent(bestOperator.ptp_conversion_pct)} PTP conversion across ${formatNumber(bestOperator.total_calls)} calls.`
                    : "Agent ranking will appear once the campaign has more operator history."}
                </Text>
              </Paper>
            </SimpleGrid>
          </Card>
        </Grid.Col>
      </Grid>
    </Card>
  );
}

function ActionInterventionSection({
  tasks,
  actions,
}: {
  tasks: TaskRow[];
  actions: QueueAction[];
}) {
  return (
    <Card className="te-command-section">
      <SectionHeader
        title="Action & Intervention Panel"
        subtitle="Immediate account-level interventions from the live campaign queue"
        icon={<Zap size={20} />}
        badge="Action center"
        badgeColor="orange"
      />

      <Grid>
        <Grid.Col span={{ base: 12, lg: 7 }}>
          <Card className="te-command-chart-card">
            <Group justify="space-between" mb="md">
              <Text size="sm" fw={600}>
                High Priority Accounts
              </Text>
              <Badge variant="light" color="red" size="sm">
                SLA-first queue
              </Badge>
            </Group>
            {tasks.length ? (
              <Stack gap="sm">
                {tasks.map((task) => (
                  <Paper
                    key={task.id}
                    p="sm"
                    radius="md"
                    style={{
                      background: "linear-gradient(135deg, rgba(239, 68, 68, 0.06), rgba(239, 68, 68, 0.02))",
                      border: "1px solid rgba(239, 68, 68, 0.12)",
                    }}
                  >
                    <Group justify="space-between" mb="xs">
                      <div>
                        <Text size="sm" fw={600}>
                          {task.customer_name || task.customer_id}
                        </Text>
                        <Text size="xs" c="dimmed">
                          {task.id}
                        </Text>
                      </div>
                      <Group gap="xs">
                        {task.state ? (
                          <Badge variant="light" color={task.state === "ESCALATED" ? "red" : task.state === "CALLBACK" ? "orange" : "blue"}>
                            {stateLabel(task.state)}
                          </Badge>
                        ) : null}
                        {task.dpd != null ? (
                          <Badge variant="outline" color={task.dpd >= 61 ? "red" : task.dpd >= 31 ? "orange" : "green"}>
                            {task.dpd} DPD
                          </Badge>
                        ) : null}
                      </Group>
                    </Group>
                    <Group gap="lg">
                      <Text size="xs" c="dimmed">
                        Due: {rupees(Number(task.amount_due || 0))}
                      </Text>
                      <Text size="xs" c="dimmed">
                        Phone: {task.phone || "-"}
                      </Text>
                      <Text size="xs" c="dimmed">
                        Owner: {task.owner || "Unassigned"}
                      </Text>
                    </Group>
                  </Paper>
                ))}
              </Stack>
            ) : (
              <EmptyStateCard
                title="No priority tasks for this scope"
                description="Adjust the task state or bucket filters, or wait for new campaign work to enter the queue."
              />
            )}
          </Card>
        </Grid.Col>

        <Grid.Col span={{ base: 12, lg: 5 }}>
          <Card className="te-command-chart-card">
            <Group justify="space-between" mb="md">
              <Text size="sm" fw={600}>
                Immediate Action Queue
              </Text>
              <Badge variant="light" color="orange" size="sm">
                Actual counts
              </Badge>
            </Group>
            <Stack gap="sm">
              {actions.map((item) => (
                <Paper
                  key={item.title}
                  p="sm"
                  radius="md"
                  style={{
                    background:
                      item.color === COLORS.danger
                        ? COLORS.dangerLight
                        : item.color === COLORS.warning
                        ? COLORS.warningLight
                        : item.color === COLORS.success
                        ? COLORS.successLight
                        : COLORS.primaryLight,
                    border: `1px solid ${item.color === COLORS.danger ? "rgba(205, 63, 70, 0.18)" : item.color === COLORS.warning ? "rgba(184, 120, 32, 0.18)" : "rgba(18, 93, 255, 0.18)"}`,
                  }}
                >
                  <Group justify="space-between" align="flex-start">
                    <Group gap="sm" align="flex-start">
                      <ThemeIcon
                        size="md"
                        variant="light"
                        color={item.color === COLORS.danger ? "red" : item.color === COLORS.warning ? "orange" : item.color === COLORS.success ? "green" : "blue"}
                        radius="md"
                      >
                        {item.icon}
                      </ThemeIcon>
                      <div>
                        <Text size="sm" fw={500}>
                          {item.title}
                        </Text>
                        <Text size="xs" c="dimmed">
                          {item.detail}
                        </Text>
                      </div>
                    </Group>
                    <Badge
                      size="lg"
                      variant="filled"
                      color={item.color === COLORS.danger ? "red" : item.color === COLORS.warning ? "orange" : item.color === COLORS.success ? "green" : "blue"}
                    >
                      {formatNumber(item.count)}
                    </Badge>
                  </Group>
                </Paper>
              ))}
            </Stack>
          </Card>
        </Grid.Col>
      </Grid>
    </Card>
  );
}

export function CommandCenterPage() {
  const [dateRange, setDateRange] = useState("last_30");
  const [campaignId, setCampaignId] = useState("");
  const [taskState, setTaskState] = useState("");
  const [bucket, setBucket] = useState("");

  const days = daysFromRange(dateRange);

  const campaigns = useQuery({
    queryKey: ["command_center_campaigns"],
    queryFn: () => apiFetch<{ rows: CampaignRow[] }>("/api/campaigns"),
    refetchInterval: LIVE_REFRESH_MS,
  });

  useEffect(() => {
    if (!campaignId && campaigns.data?.rows?.length) {
      setCampaignId(campaigns.data.rows[0].campaign_id);
    }
  }, [campaignId, campaigns.data]);

  const queriesEnabled = Boolean(campaignId);

  const metrics = useQuery({
    queryKey: ["command_center_metrics", campaignId],
    enabled: queriesEnabled,
    queryFn: () => apiFetch<MetricsResponse>(`/api/metrics${toQuery({ campaign_id: campaignId })}`),
    refetchInterval: LIVE_REFRESH_MS,
  });
  const build = useQuery({
    queryKey: ["command_center_build_info"],
    queryFn: () => apiFetch<BuildInfo>("/api/system/build_info"),
  });
  const rollForward = useQuery({
    queryKey: ["command_center_roll_forward", campaignId, days],
    enabled: queriesEnabled,
    queryFn: () => apiFetch<RollForwardResponse>(`/api/metrics/roll-forward${toQuery({ campaign_id: campaignId, days })}`),
    refetchInterval: LIVE_REFRESH_MS,
  });
  const recovery = useQuery({
    queryKey: ["command_center_recovery", campaignId, days],
    enabled: queriesEnabled,
    queryFn: () => apiFetch<RecoveryResponse>(`/api/metrics/recovery${toQuery({ campaign_id: campaignId, days })}`),
    refetchInterval: LIVE_REFRESH_MS,
  });
  const agents = useQuery({
    queryKey: ["command_center_agents", campaignId],
    enabled: queriesEnabled,
    queryFn: () => apiFetch<{ agents: AgentMetric[] }>(`/api/metrics/agents${toQuery({ campaign_id: campaignId })}`),
    refetchInterval: LIVE_REFRESH_MS,
  });
  const taskSummary = useQuery({
    queryKey: ["command_center_task_summary", campaignId],
    enabled: queriesEnabled,
    queryFn: () => apiFetch<Record<string, number>>(`/api/tasks/summary${toQuery({ campaign_id: campaignId })}`),
    refetchInterval: LIVE_REFRESH_MS,
  });
  const sessions = useQuery({
    queryKey: ["command_center_sessions", campaignId, bucket],
    enabled: queriesEnabled,
    queryFn: () => apiFetch<{ sessions: SessionSnapshot[] }>(`/api/sessions${toQuery({ campaign_id: campaignId, bucket })}`),
    refetchInterval: LIVE_REFRESH_MS,
  });
  const tasks = useQuery({
    queryKey: ["command_center_tasks", campaignId, taskState, bucket],
    enabled: queriesEnabled,
    queryFn: () =>
      apiFetch<ApiListResponse<TaskRow>>(
        `/api/tasks${toQuery({ campaign_id: campaignId, state: taskState, dpd_bucket: bucket, sort: "sla_asc", page: 1, page_size: 6 })}`
      ),
    refetchInterval: LIVE_REFRESH_MS,
  });

  const selectedCampaign = useMemo(
    () => (campaigns.data?.rows || []).find((row) => row.campaign_id === campaignId) || null,
    [campaignId, campaigns.data],
  );

  const campaignOptions = useMemo(
    () => (campaigns.data?.rows || []).map((row) => ({ value: row.campaign_id, label: `${row.name || row.campaign_id} (${row.campaign_id})` })),
    [campaigns.data],
  );

  const essentialLoading =
    campaigns.isLoading ||
    (!campaignId && Boolean(campaigns.data?.rows?.length)) ||
    (queriesEnabled &&
      (metrics.isLoading ||
        rollForward.isLoading ||
        recovery.isLoading ||
        agents.isLoading ||
        taskSummary.isLoading ||
        sessions.isLoading ||
        tasks.isLoading));

  const blockingError =
    campaigns.error ||
    metrics.error ||
    rollForward.error ||
    recovery.error ||
    agents.error ||
    taskSummary.error ||
    sessions.error ||
    tasks.error;

  if (campaigns.isLoading || (!campaignId && Boolean(campaigns.data?.rows?.length))) {
    return (
      <Group justify="center" py="xl">
        <Loader />
      </Group>
    );
  }

  if (!campaigns.data?.rows?.length) {
    return (
      <Stack gap="md" className="te-command-center">
        <ModuleHeader
          title="AI Collections Command Center"
          subtitle="Campaign-level control room for collections, recovery, and intervention"
          badge="Mission Control"
        />
        <EmptyStateCard
          title="No campaigns available"
          description="Create or launch a campaign first. The AI Command Center now reads directly from live campaign metrics instead of seeded demo values."
        />
      </Stack>
    );
  }

  if (essentialLoading) {
    return (
      <Group justify="center" py="xl">
        <Loader />
      </Group>
    );
  }

  if (
    blockingError ||
    !selectedCampaign ||
    !metrics.data ||
    !rollForward.data ||
    !recovery.data ||
    !agents.data ||
    !taskSummary.data ||
    !sessions.data ||
    !tasks.data
  ) {
    return (
      <Stack gap="md" className="te-command-center">
        <ModuleHeader
          title="AI Collections Command Center"
          subtitle="Campaign-level control room for collections, recovery, and intervention"
          badge="Mission Control"
        />
        <Card className="te-command-section">
          <Text c="red" fw={600}>
            Unable to load campaign-backed command center metrics.
          </Text>
          <Text size="sm" c="dimmed" mt="xs">
            {blockingError instanceof Error ? blockingError.message : "The selected campaign could not be resolved."}
          </Text>
        </Card>
      </Stack>
    );
  }

  const m = metrics.data;
  const queueRows = TASK_STATE_ORDER.map((state) => ({
    state,
    count: Number(taskSummary.data[state] ?? m.queue_snapshot?.[state] ?? 0),
    color: STATE_COLORS[state],
  }));
  const bucketRows: BucketMetric[] = ["1-30", "31-60", "61-90", "90+"].map((bucketName) => {
    const exposure = Number(m.bucket_heatmap?.[bucketName] || 0);
    const total = Number(m.ptp_rate_by_bucket?.[bucketName]?.total || 0);
    const ptpCount = Number(m.ptp_rate_by_bucket?.[bucketName]?.ptp || 0);
    return {
      bucket: bucketName,
      exposure,
      share: 0,
      ptpRate: Number(m.ptp_rate_by_bucket?.[bucketName]?.rate || 0),
      ptpCount,
      ptpTotal: total,
      color: BUCKET_COLORS[bucketName],
    };
  });
  const totalBucketExposure = bucketRows.reduce((sum, item) => sum + item.exposure, 0);
  bucketRows.forEach((item) => {
    item.share = totalBucketExposure > 0 ? (item.exposure / totalBucketExposure) * 100 : 0;
  });

  const recommendationCandidates = [
    {
      rawCount: Number(taskSummary.data.CALLBACK || 0),
      title: "Clear overdue callback queue",
      countLabel: `${formatNumber(Number(taskSummary.data.CALLBACK || 0))} open`,
      detail: "Callback work is still open in the campaign and is slowing closure discipline.",
      color: COLORS.warning,
      icon: <PhoneCall size={16} />,
    },
    {
      rawCount: Number(m.bucket_heatmap?.["31-60"] || 0),
      title: "Stabilize the 31-60 bucket",
      countLabel: `${formatNumber(Number(m.bucket_heatmap?.["31-60"] || 0))} accounts`,
      detail: "This mid-bucket lane carries the largest recoverable exposure and usually drives the next roll-forward spike.",
      color: COLORS.primary,
      icon: <Layers size={16} />,
    },
    {
      rawCount: Number(m.sla_breaches || 0),
      title: "Close SLA breach inventory",
      countLabel: `${formatNumber(Number(m.sla_breaches || 0))} breaches`,
      detail: "Open SLA breaches are active service-level failures and should not sit behind normal queue work.",
      color: COLORS.danger,
      icon: <Clock size={16} />,
    },
    {
      rawCount: Number(m.retries_pending || 0),
      title: "Work retry-scheduled accounts",
      countLabel: `${formatNumber(Number(m.retries_pending || 0))} retries`,
      detail: "Retry-scheduled borrowers are already in the campaign and need fresh contact attempts to avoid stalling the book.",
      color: COLORS.teal,
      icon: <RefreshCw size={16} />,
    },
  ];
  const recommendationRows: RecommendationTileProps[] = recommendationCandidates
    .filter((item) => item.rawCount > 0)
    .map(({ rawCount: _rawCount, ...item }) => item);

  const actions: QueueAction[] = [
    {
      title: "SLA breaches",
      count: Number(m.sla_breaches || 0),
      detail: "Tasks already outside their service threshold.",
      color: COLORS.danger,
      icon: <Clock size={16} />,
    },
    {
      title: "Callback queue",
      count: Number(taskSummary.data.CALLBACK || 0),
      detail: "Borrowers waiting for a promised follow-up.",
      color: COLORS.warning,
      icon: <PhoneCall size={16} />,
    },
    {
      title: "Retry-scheduled",
      count: Number(m.retries_pending || 0),
      detail: "Accounts paused for another contact attempt.",
      color: COLORS.primary,
      icon: <RefreshCw size={16} />,
    },
    {
      title: "PTP misses",
      count: Number(m.ptp_miss_open_alerts || 0),
      detail: "Open alerts where commitments are already slipping.",
      color: COLORS.success,
      icon: <Target size={16} />,
    },
  ].filter((item) => item.count > 0);

  return (
    <Stack gap="md" className="te-command-center">
      <ModuleHeader
        title="AI Collections Command Center"
        subtitle="Campaign-level collections intelligence grounded in actual queue, recovery, and session metrics"
        badge="Mission Control"
        action={
          <Group gap="sm">
            <Menu shadow="md" width={220}>
              <Menu.Target>
                <Button variant="light" leftSection={<Download size={16} />} rightSection={<ChevronDown size={14} />}>
                  Export
                </Button>
              </Menu.Target>
              <Menu.Dropdown>
                <Menu.Label>Export Options</Menu.Label>
                <Menu.Item leftSection={<FileSpreadsheet size={14} />}>Export to Excel</Menu.Item>
                <Menu.Item leftSection={<Download size={14} />}>Export to PDF</Menu.Item>
              </Menu.Dropdown>
            </Menu>
            <Badge variant="filled" color="green" size="lg">
              {selectedCampaign.name || selectedCampaign.campaign_id}
            </Badge>
            <Badge variant="outline" color="blue" size="lg">
              Build {build.data?.static_token || "-"}
            </Badge>
          </Group>
        }
      />

      <GlobalFilters
        dateRange={dateRange}
        setDateRange={setDateRange}
        campaignId={campaignId}
        setCampaignId={setCampaignId}
        campaignOptions={campaignOptions}
        taskState={taskState}
        setTaskState={setTaskState}
        bucket={bucket}
        setBucket={setBucket}
      />

      <PortfolioHealthSection metrics={m} recovery={recovery.data} queueRows={queueRows} selectedCampaign={selectedCampaign} />
      <DelinquencyRiskSection bucketRows={bucketRows} rollForward={rollForward.data} />
      <RecoveryPerformanceSection metrics={m} recovery={recovery.data} agents={agents.data.agents} />
      <CollectionsOperationsSection metrics={m} queueRows={queueRows} agents={agents.data.agents} sessions={sessions.data.sessions} />
      <AIDecisionIntelligenceSection
        bucketRows={bucketRows}
        metrics={m}
        recovery={recovery.data}
        rollForward={rollForward.data}
        agents={agents.data.agents}
        recommendations={
          recommendationRows.length
            ? recommendationRows
            : [
                {
                  title: "Campaign is within current guardrails",
                  countLabel: "Stable",
                  detail: "No major exception queue is open right now. Continue monitoring live sessions and fresh movement signals.",
                  color: COLORS.success,
                  icon: <Brain size={16} />,
                },
              ]
        }
      />
      <ActionInterventionSection tasks={tasks.data.rows} actions={actions.length ? actions : [{ title: "No immediate action pressure", count: 0, detail: "The current filtered queue does not contain open intervention backlogs.", color: COLORS.success, icon: <Zap size={16} /> }]} />
    </Stack>
  );
}
