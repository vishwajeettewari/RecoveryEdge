import {
  ActionIcon,
  Badge,
  Button,
  Card,
  Collapse,
  Grid,
  Group,
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
import {
  AlertTriangle,
  ArrowUpRight,
  Brain,
  Calendar,
  ChevronDown,
  Clock,
  Download,
  FileSpreadsheet,
  Filter,
  Landmark,
  Layers,
  MapPin,
  Phone,
  PhoneCall,
  RefreshCw,
  Scale,
  Send,
  Target,
  TrendingDown,
  TrendingUp,
  User,
  UserCheck,
  Users,
  Wallet,
  Zap,
} from "lucide-react";
import { useState } from "react";
import {
  Area,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ComposedChart,
  LabelList,
  Legend,
  Line,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip as RechartsTooltip,
  XAxis,
  YAxis,
} from "recharts";

import { ModuleHeader } from "../../components/ModuleHeader";

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

const BUCKET_COLORS = {
  "0-30": "#22c55e",
  "31-60": "#eab308",
  "61-90": "#f97316",
  "90-180": "#ef4444",
  "180+": "#991b1b",
};

const RISK_COLORS = {
  low: "#22c55e",
  medium: "#eab308",
  high: "#f97316",
  severe: "#ef4444",
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

interface KPICardProps {
  label: string;
  value: string | number;
  subValue?: string;
  trend?: number;
  trendLabel?: string;
  icon?: React.ReactNode;
  color?: string;
  onClick?: () => void;
}

function KPICard({ label, value, subValue, trend, trendLabel, icon, color = COLORS.primary, onClick }: KPICardProps) {
  const TrendIcon = trend && trend > 0 ? TrendingUp : trend && trend < 0 ? TrendingDown : null;
  const trendColor = trend && trend > 0 ? COLORS.success : trend && trend < 0 ? COLORS.danger : COLORS.slate;

  return (
    <Card
      className="te-command-kpi"
      onClick={onClick}
      style={{ cursor: onClick ? "pointer" : "default" }}
    >
      <Group justify="space-between" align="flex-start" mb="xs">
        <Text size="xs" tt="uppercase" fw={700} c="dimmed" style={{ letterSpacing: "0.06em" }}>
          {label}
        </Text>
        {icon && (
          <ThemeIcon size="sm" variant="light" color="blue" radius="md">
            {icon}
          </ThemeIcon>
        )}
      </Group>
      <Title order={2} style={{ color, letterSpacing: "-0.02em" }}>
        {value}
      </Title>
      {(subValue || trend !== undefined) && (
        <Group gap="xs" mt="xs">
          {trend !== undefined && TrendIcon && (
            <Badge
              variant="light"
              color={trend > 0 ? "green" : "red"}
              size="sm"
              leftSection={<TrendIcon size={12} />}
            >
              {Math.abs(trend).toFixed(1)}%
            </Badge>
          )}
          {subValue && (
            <Text size="xs" c="dimmed">
              {subValue}
            </Text>
          )}
        </Group>
      )}
    </Card>
  );
}

interface SectionHeaderProps {
  title: string;
  subtitle?: string;
  icon: React.ReactNode;
  badge?: string;
  badgeColor?: string;
  action?: React.ReactNode;
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
            {badge && (
              <Badge variant="light" color={badgeColor} size="sm">
                {badge}
              </Badge>
            )}
          </Group>
          {subtitle && (
            <Text size="sm" c="dimmed">
              {subtitle}
            </Text>
          )}
        </div>
      </Group>
      {action}
    </Group>
  );
}

function GlobalFilters({
  dateRange,
  setDateRange,
  region,
  setRegion,
  portfolio,
  setPortfolio,
  bucket,
  setBucket,
}: {
  dateRange: string;
  setDateRange: (v: string) => void;
  region: string;
  setRegion: (v: string) => void;
  portfolio: string;
  setPortfolio: (v: string) => void;
  bucket: string;
  setBucket: (v: string) => void;
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
              Apply filters across all dashboard sections
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
              setRegion("");
              setPortfolio("");
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
            onChange={(v) => setDateRange(v || "last_30")}
            data={[
              { value: "today", label: "Today" },
              { value: "last_7", label: "Last 7 Days" },
              { value: "last_30", label: "Last 30 Days" },
              { value: "last_90", label: "Last 90 Days" },
              { value: "custom", label: "Custom Range" },
            ]}
            leftSection={<Calendar size={16} />}
          />
          <Select
            label="Region"
            placeholder="All Regions"
            value={region}
            onChange={(v) => setRegion(v || "")}
            data={[
              { value: "", label: "All Regions" },
              { value: "north", label: "North India" },
              { value: "south", label: "South India" },
              { value: "east", label: "East India" },
              { value: "west", label: "West India" },
            ]}
            leftSection={<MapPin size={16} />}
            clearable
          />
          <Select
            label="Portfolio"
            placeholder="All Portfolios"
            value={portfolio}
            onChange={(v) => setPortfolio(v || "")}
            data={[
              { value: "", label: "All Portfolios" },
              { value: "personal_loan", label: "Personal Loans" },
              { value: "business_loan", label: "Business Loans" },
              { value: "vehicle_loan", label: "Vehicle Loans" },
              { value: "credit_card", label: "Credit Cards" },
            ]}
            leftSection={<Wallet size={16} />}
            clearable
          />
          <Select
            label="Delinquency Bucket"
            placeholder="All Buckets"
            value={bucket}
            onChange={(v) => setBucket(v || "")}
            data={[
              { value: "", label: "All Buckets" },
              { value: "0-30", label: "0-30 DPD" },
              { value: "31-60", label: "31-60 DPD" },
              { value: "61-90", label: "61-90 DPD" },
              { value: "90-180", label: "90-180 DPD" },
              { value: "180+", label: "180+ DPD" },
            ]}
            leftSection={<Layers size={16} />}
            clearable
          />
        </SimpleGrid>
      </Collapse>
    </Paper>
  );
}

function PortfolioHealthSection() {
  const portfolioData = {
    totalLoanBook: 245000000000,
    activeLoans: 1250000,
    overdueAmount: 18500000000,
    npaAmount: 8200000000,
    npaRatio: 3.35,
    expectedRecovery: 4500000000,
    recoveryThisMonth: 2800000000,
  };

  const trendData = [
    { month: "Aug", total: 220, delinquent: 15, recovered: 2.1 },
    { month: "Sep", total: 228, delinquent: 16, recovered: 2.4 },
    { month: "Oct", total: 235, delinquent: 17, recovered: 2.6 },
    { month: "Nov", total: 240, delinquent: 18, recovered: 2.5 },
    { month: "Dec", total: 242, delinquent: 18.2, recovered: 2.7 },
    { month: "Jan", total: 245, delinquent: 18.5, recovered: 2.8 },
  ];

  return (
    <Card className="te-command-section">
      <SectionHeader
        title="Portfolio Health Overview"
        subtitle="Real-time snapshot of the loan portfolio"
        icon={<Landmark size={20} />}
        badge="Live"
        badgeColor="green"
      />

      <SimpleGrid cols={{ base: 2, sm: 3, lg: 7 }} spacing="md" mb="lg">
        <KPICard
          label="Total Loan Book"
          value={rupeesCompact(portfolioData.totalLoanBook)}
          subValue="Outstanding principal"
          trend={2.1}
          icon={<Wallet size={14} />}
        />
        <KPICard
          label="Active Loans"
          value={formatNumber(portfolioData.activeLoans)}
          subValue="Current accounts"
          trend={1.8}
          icon={<Users size={14} />}
        />
        <KPICard
          label="Total Overdue"
          value={rupeesCompact(portfolioData.overdueAmount)}
          subValue="Pending payments"
          trend={-3.2}
          icon={<Clock size={14} />}
          color={COLORS.warning}
        />
        <KPICard
          label="NPA Amount"
          value={rupeesCompact(portfolioData.npaAmount)}
          subValue={`${portfolioData.npaRatio}% of portfolio`}
          trend={-1.5}
          icon={<AlertTriangle size={14} />}
          color={COLORS.danger}
        />
        <KPICard
          label="Expected Recovery"
          value={rupeesCompact(portfolioData.expectedRecovery)}
          subValue="Next 30 days (AI)"
          icon={<Brain size={14} />}
          color={COLORS.teal}
        />
        <KPICard
          label="Recovery MTD"
          value={rupeesCompact(portfolioData.recoveryThisMonth)}
          subValue="This month"
          trend={12.4}
          icon={<TrendingUp size={14} />}
          color={COLORS.success}
        />
        <KPICard
          label="Recovery Rate"
          value={percent(15.1)}
          subValue="vs 13.2% last month"
          trend={14.4}
          icon={<Target size={14} />}
          color={COLORS.success}
        />
      </SimpleGrid>

      <Card className="te-command-chart-card">
        <Group justify="space-between" mb="md">
          <Text size="sm" fw={600}>
            Portfolio Trend (₹ in Cr)
          </Text>
          <Badge variant="light" size="sm">
            6 Months
          </Badge>
        </Group>
        <div style={{ height: 280 }}>
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={trendData}>
              <CartesianGrid strokeDasharray="3 3" stroke={CHART_THEME.grid} />
              <XAxis dataKey="month" tick={CHART_AXIS_TICK} axisLine={CHART_AXIS_LINE} tickLine={CHART_AXIS_LINE} />
              <YAxis yAxisId="left" tick={CHART_AXIS_TICK} axisLine={CHART_AXIS_LINE} tickLine={CHART_AXIS_LINE} />
              <YAxis yAxisId="right" orientation="right" tick={CHART_AXIS_TICK} axisLine={CHART_AXIS_LINE} tickLine={CHART_AXIS_LINE} />
              <RechartsTooltip
                contentStyle={CHART_TOOLTIP_STYLE}
                labelStyle={CHART_TOOLTIP_TEXT_STYLE}
                itemStyle={CHART_TOOLTIP_TEXT_STYLE}
              />
              <Legend />
              <Area
                yAxisId="left"
                type="monotone"
                dataKey="total"
                name="Total Portfolio"
                fill={COLORS.primaryLight}
                stroke={COLORS.primary}
                strokeWidth={2}
              />
              <Area
                yAxisId="left"
                type="monotone"
                dataKey="delinquent"
                name="Delinquent"
                fill={COLORS.dangerLight}
                stroke={COLORS.danger}
                strokeWidth={2}
              />
              <Line
                yAxisId="right"
                type="monotone"
                dataKey="recovered"
                name="Recovered"
                stroke={COLORS.success}
                strokeWidth={3}
                dot={{ fill: COLORS.success, r: 4 }}
              />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      </Card>
    </Card>
  );
}

function DelinquencyRiskSection() {
  const bucketData = [
    { bucket: "0-30 DPD", count: 45000, amount: 4500, color: BUCKET_COLORS["0-30"] },
    { bucket: "31-60 DPD", count: 28000, amount: 3200, color: BUCKET_COLORS["31-60"] },
    { bucket: "61-90 DPD", count: 15000, amount: 2800, color: BUCKET_COLORS["61-90"] },
    { bucket: "90-180 DPD", count: 8500, amount: 4200, color: BUCKET_COLORS["90-180"] },
    { bucket: "180+ DPD", count: 5200, amount: 3800, color: BUCKET_COLORS["180+"] },
  ];

  const parData = [
    { metric: "PAR 30", value: 7.55, target: 8.0, status: "healthy" },
    { metric: "PAR 60", value: 4.82, target: 5.0, status: "healthy" },
    { metric: "PAR 90", value: 3.35, target: 3.5, status: "warning" },
  ];

  const rollRateData = [
    { from: "Current", to_30: 92, to_60: 5, to_90: 2, to_npa: 1 },
    { from: "0-30 DPD", to_30: 45, to_60: 38, to_90: 12, to_npa: 5 },
    { from: "31-60 DPD", to_30: 22, to_60: 35, to_90: 28, to_npa: 15 },
    { from: "61-90 DPD", to_30: 12, to_60: 18, to_90: 35, to_npa: 35 },
  ];

  const regionRiskData = [
    { region: "Maharashtra", risk: "high", delinquency: 8.2, accounts: 125000 },
    { region: "Karnataka", risk: "medium", delinquency: 5.4, accounts: 98000 },
    { region: "Tamil Nadu", risk: "low", delinquency: 3.2, accounts: 112000 },
    { region: "Delhi NCR", risk: "high", delinquency: 7.8, accounts: 145000 },
    { region: "Gujarat", risk: "medium", delinquency: 4.9, accounts: 87000 },
    { region: "West Bengal", risk: "high", delinquency: 9.1, accounts: 76000 },
  ];

  return (
    <Card className="te-command-section">
      <SectionHeader
        title="Delinquency & Risk Intelligence"
        subtitle="Identify where risk is emerging across the portfolio"
        icon={<AlertTriangle size={20} />}
        badge="Risk Monitor"
        badgeColor="orange"
      />

      <Grid>
        <Grid.Col span={{ base: 12, lg: 6 }}>
          <Card className="te-command-chart-card">
            <Group justify="space-between" mb="md">
              <Text size="sm" fw={600}>
                Delinquency Bucket Distribution
              </Text>
              <Badge variant="light" size="sm">
                By DPD
              </Badge>
            </Group>
            <div style={{ height: 280 }}>
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={bucketData} layout="vertical">
                  <CartesianGrid strokeDasharray="3 3" stroke={CHART_THEME.grid} />
                  <XAxis type="number" tick={CHART_AXIS_TICK} axisLine={CHART_AXIS_LINE} tickLine={CHART_AXIS_LINE} />
                  <YAxis dataKey="bucket" type="category" tick={CHART_AXIS_TICK_SMALL} axisLine={CHART_AXIS_LINE} tickLine={CHART_AXIS_LINE} width={80} />
                  <RechartsTooltip
                    contentStyle={CHART_TOOLTIP_STYLE}
                    labelStyle={CHART_TOOLTIP_TEXT_STYLE}
                    itemStyle={CHART_TOOLTIP_TEXT_STYLE}
                    formatter={(value, name) => [
                      name === "count" ? formatNumber(Number(value)) : `₹${value}Cr`,
                      name === "count" ? "Accounts" : "Amount",
                    ]}
                  />
                  <Bar dataKey="count" name="count" radius={[0, 4, 4, 0]}>
                    {bucketData.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={entry.color} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </Card>
        </Grid.Col>

        <Grid.Col span={{ base: 12, lg: 6 }}>
          <Card className="te-command-chart-card">
            <Group justify="space-between" mb="md">
              <Text size="sm" fw={600}>
                Portfolio at Risk (PAR)
              </Text>
              <Badge variant="light" size="sm">
                vs Target
              </Badge>
            </Group>
            <Stack gap="lg" mt="md">
              {parData.map((item) => (
                <div key={item.metric}>
                  <Group justify="space-between" mb="xs">
                    <Text size="sm" fw={500}>
                      {item.metric}
                    </Text>
                    <Group gap="xs">
                      <Text size="sm" fw={700} c={item.status === "healthy" ? "green" : "orange"}>
                        {item.value}%
                      </Text>
                      <Text size="xs" c="dimmed">
                        / {item.target}% target
                      </Text>
                    </Group>
                  </Group>
                  <Progress.Root size="lg" radius="xl">
                    <Progress.Section
                      value={(item.value / item.target) * 100}
                      color={item.status === "healthy" ? "green" : "orange"}
                    />
                  </Progress.Root>
                </div>
              ))}
            </Stack>
          </Card>
        </Grid.Col>

        <Grid.Col span={{ base: 12, lg: 7 }}>
          <Card className="te-command-chart-card">
            <Group justify="space-between" mb="md">
              <Text size="sm" fw={600}>
                Roll Rate Matrix
              </Text>
              <Badge variant="light" size="sm">
                30-Day Transitions
              </Badge>
            </Group>
            <ScrollArea>
              <Table className="te-command-matrix-table">
                <Table.Thead>
                  <Table.Tr>
                    <Table.Th>From / To</Table.Th>
                    <Table.Th style={{ textAlign: "center" }}>Stay/Cure</Table.Th>
                    <Table.Th style={{ textAlign: "center" }}>→ 31-60</Table.Th>
                    <Table.Th style={{ textAlign: "center" }}>→ 61-90</Table.Th>
                    <Table.Th style={{ textAlign: "center" }}>→ NPA</Table.Th>
                  </Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {rollRateData.map((row) => (
                    <Table.Tr key={row.from}>
                      <Table.Td fw={600}>{row.from}</Table.Td>
                      <Table.Td
                        style={{
                          textAlign: "center",
                          background: `rgba(34, 197, 94, ${row.to_30 / 100 * 0.3})`,
                        }}
                      >
                        {row.to_30}%
                      </Table.Td>
                      <Table.Td
                        style={{
                          textAlign: "center",
                          background: `rgba(234, 179, 8, ${row.to_60 / 100 * 0.4})`,
                        }}
                      >
                        {row.to_60}%
                      </Table.Td>
                      <Table.Td
                        style={{
                          textAlign: "center",
                          background: `rgba(249, 115, 22, ${row.to_90 / 100 * 0.4})`,
                        }}
                      >
                        {row.to_90}%
                      </Table.Td>
                      <Table.Td
                        style={{
                          textAlign: "center",
                          background: `rgba(239, 68, 68, ${row.to_npa / 100 * 0.5})`,
                        }}
                      >
                        {row.to_npa}%
                      </Table.Td>
                    </Table.Tr>
                  ))}
                </Table.Tbody>
              </Table>
            </ScrollArea>
          </Card>
        </Grid.Col>

        <Grid.Col span={{ base: 12, lg: 5 }}>
          <Card className="te-command-chart-card">
            <Group justify="space-between" mb="md">
              <Text size="sm" fw={600}>
                Geographic Risk Map
              </Text>
              <Badge variant="light" size="sm">
                By Region
              </Badge>
            </Group>
            <ScrollArea style={{ height: 240 }}>
              <Stack gap="xs">
                {regionRiskData.map((item) => (
                  <Paper
                    key={item.region}
                    p="sm"
                    radius="md"
                    style={{
                      background:
                        item.risk === "high"
                          ? COLORS.dangerLight
                          : item.risk === "medium"
                          ? COLORS.warningLight
                          : COLORS.successLight,
                      border: `1px solid ${
                        item.risk === "high"
                          ? "rgba(205, 63, 70, 0.2)"
                          : item.risk === "medium"
                          ? "rgba(184, 120, 32, 0.2)"
                          : "rgba(31, 143, 90, 0.2)"
                      }`,
                    }}
                  >
                    <Group justify="space-between">
                      <Group gap="xs">
                        <MapPin
                          size={14}
                          color={
                            item.risk === "high"
                              ? COLORS.danger
                              : item.risk === "medium"
                              ? COLORS.warning
                              : COLORS.success
                          }
                        />
                        <Text size="sm" fw={500}>
                          {item.region}
                        </Text>
                      </Group>
                      <Group gap="md">
                        <Text size="xs" c="dimmed">
                          {formatNumber(item.accounts)} accounts
                        </Text>
                        <Badge
                          size="sm"
                          color={
                            item.risk === "high" ? "red" : item.risk === "medium" ? "orange" : "green"
                          }
                        >
                          {item.delinquency}% DQ
                        </Badge>
                      </Group>
                    </Group>
                  </Paper>
                ))}
              </Stack>
            </ScrollArea>
          </Card>
        </Grid.Col>
      </Grid>
    </Card>
  );
}

function RecoveryPerformanceSection() {
  const recoveryMetrics = {
    recoveryRate: 15.1,
    collectionEfficiency: 78.4,
    cureRate: 22.3,
  };

  const funnelData = [
    { name: "Total Overdue", value: 101700, fill: COLORS.primary },
    { name: "Contacted", value: 78500, fill: COLORS.info },
    { name: "Promise to Pay", value: 42000, fill: COLORS.teal },
    { name: "Actual Payment", value: 28500, fill: COLORS.success },
    { name: "Fully Recovered", value: 15400, fill: "#16a34a" },
  ];

  const channelData = [
    { channel: "Digital Payments", amount: 1200, percentage: 42.8 },
    { channel: "Call Center", amount: 850, percentage: 30.4 },
    { channel: "Field Collection", amount: 520, percentage: 18.6 },
    { channel: "Legal Recovery", amount: 230, percentage: 8.2 },
  ];

  const recoveryTrendData = [
    { week: "W1", target: 650, actual: 580 },
    { week: "W2", target: 680, actual: 720 },
    { week: "W3", target: 700, actual: 695 },
    { week: "W4", target: 720, actual: 805 },
  ];

  return (
    <Card className="te-command-section">
      <SectionHeader
        title="Recovery Performance"
        subtitle="Measure effectiveness of recovery operations"
        icon={<Target size={20} />}
        badge="Performance"
        badgeColor="green"
      />

      <SimpleGrid cols={{ base: 1, sm: 3 }} spacing="md" mb="lg">
        <Card className="te-command-metric-card">
          <Group justify="space-between" align="flex-start">
            <div>
              <Text size="xs" tt="uppercase" fw={700} c="dimmed">
                Recovery Rate
              </Text>
              <Title order={2} c={COLORS.success} mt="xs">
                {recoveryMetrics.recoveryRate}%
              </Title>
              <Text size="xs" c="dimmed" mt="xs">
                Amount Recovered / Total Overdue
              </Text>
            </div>
            <RingProgress
              size={80}
              thickness={8}
              roundCaps
              sections={[{ value: recoveryMetrics.recoveryRate, color: COLORS.success }]}
              label={
                <Text size="xs" ta="center" fw={700}>
                  {recoveryMetrics.recoveryRate}%
                </Text>
              }
            />
          </Group>
        </Card>

        <Card className="te-command-metric-card">
          <Group justify="space-between" align="flex-start">
            <div>
              <Text size="xs" tt="uppercase" fw={700} c="dimmed">
                Collection Efficiency
              </Text>
              <Title order={2} c={COLORS.primary} mt="xs">
                {recoveryMetrics.collectionEfficiency}%
              </Title>
              <Text size="xs" c="dimmed" mt="xs">
                Collected / Total Collectible
              </Text>
            </div>
            <RingProgress
              size={80}
              thickness={8}
              roundCaps
              sections={[{ value: recoveryMetrics.collectionEfficiency, color: COLORS.primary }]}
              label={
                <Text size="xs" ta="center" fw={700}>
                  {recoveryMetrics.collectionEfficiency}%
                </Text>
              }
            />
          </Group>
        </Card>

        <Card className="te-command-metric-card">
          <Group justify="space-between" align="flex-start">
            <div>
              <Text size="xs" tt="uppercase" fw={700} c="dimmed">
                Cure Rate
              </Text>
              <Title order={2} c={COLORS.teal} mt="xs">
                {recoveryMetrics.cureRate}%
              </Title>
              <Text size="xs" c="dimmed" mt="xs">
                Delinquent → Current
              </Text>
            </div>
            <RingProgress
              size={80}
              thickness={8}
              roundCaps
              sections={[{ value: recoveryMetrics.cureRate, color: COLORS.teal }]}
              label={
                <Text size="xs" ta="center" fw={700}>
                  {recoveryMetrics.cureRate}%
                </Text>
              }
            />
          </Group>
        </Card>
      </SimpleGrid>

      <Grid>
        <Grid.Col span={{ base: 12, lg: 6 }}>
          <Card className="te-command-chart-card">
            <Group justify="space-between" mb="md">
              <Text size="sm" fw={600}>
                Recovery Funnel
              </Text>
              <Badge variant="light" size="sm">
                Conversion Flow
              </Badge>
            </Group>
            <Stack gap="sm">
              {funnelData.map((item, index) => {
                const widthPercent = (item.value / funnelData[0].value) * 100;
                const conversionRate =
                  index > 0
                    ? ((item.value / funnelData[index - 1].value) * 100).toFixed(1)
                    : "100";
                return (
                  <div key={item.name}>
                    <Group justify="space-between" mb={4}>
                      <Text size="xs" fw={500}>
                        {item.name}
                      </Text>
                      <Group gap="xs">
                        <Text size="xs" c="dimmed">
                          {formatNumber(item.value)}
                        </Text>
                        {index > 0 && (
                          <Badge size="xs" variant="light" color="blue">
                            {conversionRate}%
                          </Badge>
                        )}
                      </Group>
                    </Group>
                    <div
                      style={{
                        height: 28,
                        background: CHART_THEME.trackBg,
                        border: `1px solid ${CHART_THEME.subtleBorder}`,
                        borderRadius: 6,
                        overflow: "hidden",
                      }}
                    >
                      <div
                        style={{
                          width: `${widthPercent}%`,
                          height: "100%",
                          background: item.fill,
                          borderRadius: 6,
                          transition: "width 500ms ease",
                        }}
                      />
                    </div>
                  </div>
                );
              })}
            </Stack>
          </Card>
        </Grid.Col>

        <Grid.Col span={{ base: 12, lg: 6 }}>
          <Card className="te-command-chart-card">
            <Group justify="space-between" mb="md">
              <Text size="sm" fw={600}>
                Recovery by Channel
              </Text>
              <Badge variant="light" size="sm">
                ₹ in Cr
              </Badge>
            </Group>
            <div style={{ height: 260 }}>
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={channelData} layout="vertical">
                  <CartesianGrid strokeDasharray="3 3" stroke={CHART_THEME.grid} />
                  <XAxis type="number" tick={CHART_AXIS_TICK} axisLine={CHART_AXIS_LINE} tickLine={CHART_AXIS_LINE} />
                  <YAxis dataKey="channel" type="category" tick={CHART_AXIS_TICK_SMALL} axisLine={CHART_AXIS_LINE} tickLine={CHART_AXIS_LINE} width={110} />
                  <RechartsTooltip
                    contentStyle={CHART_TOOLTIP_STYLE}
                    labelStyle={CHART_TOOLTIP_TEXT_STYLE}
                    itemStyle={CHART_TOOLTIP_TEXT_STYLE}
                    formatter={(value) => [`₹${value}Cr`, "Amount"]}
                  />
                  <Bar dataKey="amount" fill={COLORS.primary} radius={[0, 4, 4, 0]}>
                    <LabelList
                      dataKey="percentage"
                      position="right"
                      formatter={(v: number) => `${v}%`}
                      style={{ fontSize: 11, fill: CHART_THEME.axisText }}
                    />
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </Card>
        </Grid.Col>
      </Grid>
    </Card>
  );
}

function CollectionsOperationsSection() {
  const operationsData = {
    totalAttempts: 485000,
    contactRate: 64.2,
    rpcRate: 48.5,
    ptpGiven: 42000,
    ptpRate: 32.8,
    ptpFulfilled: 67.4,
    ptpBroken: 18.2,
    fieldVisitEffectiveness: 45.6,
  };

  const attemptBreakdown = [
    { channel: "Phone", attempts: 285000, success: 68.2, color: COLORS.primary },
    { channel: "WhatsApp", attempts: 125000, success: 72.4, color: COLORS.teal },
    { channel: "SMS", attempts: 52000, success: 12.8, color: COLORS.info },
    { channel: "Field Visit", attempts: 23000, success: 45.6, color: COLORS.purple },
  ];

  const ptpTrendData = [
    { day: "Mon", given: 6200, fulfilled: 4100, broken: 1200 },
    { day: "Tue", given: 6800, fulfilled: 4500, broken: 1100 },
    { day: "Wed", given: 5900, fulfilled: 4000, broken: 1050 },
    { day: "Thu", given: 7200, fulfilled: 4800, broken: 1300 },
    { day: "Fri", given: 7500, fulfilled: 5100, broken: 1400 },
    { day: "Sat", given: 4800, fulfilled: 3200, broken: 850 },
    { day: "Sun", given: 3600, fulfilled: 2400, broken: 700 },
  ];

  return (
    <Card className="te-command-section">
      <SectionHeader
        title="Collections Operations Monitoring"
        subtitle="Monitor operational efficiency of collections teams"
        icon={<PhoneCall size={20} />}
        badge="Operations"
        badgeColor="blue"
      />

      <SimpleGrid cols={{ base: 2, sm: 4 }} spacing="md" mb="lg">
        <KPICard
          label="Total Attempts"
          value={formatNumber(operationsData.totalAttempts)}
          subValue="This month"
          icon={<Phone size={14} />}
        />
        <KPICard
          label="Contact Rate"
          value={percent(operationsData.contactRate)}
          subValue="Successful contacts"
          trend={3.2}
          icon={<UserCheck size={14} />}
          color={COLORS.success}
        />
        <KPICard
          label="RPC Rate"
          value={percent(operationsData.rpcRate)}
          subValue="Right party contact"
          trend={1.8}
          icon={<User size={14} />}
          color={COLORS.teal}
        />
        <KPICard
          label="Field Effectiveness"
          value={percent(operationsData.fieldVisitEffectiveness)}
          subValue="Payment per visit"
          trend={5.4}
          icon={<MapPin size={14} />}
          color={COLORS.purple}
        />
      </SimpleGrid>

      <Grid>
        <Grid.Col span={{ base: 12, lg: 5 }}>
          <Card className="te-command-chart-card">
            <Group justify="space-between" mb="md">
              <Text size="sm" fw={600}>
                Contact Attempts by Channel
              </Text>
              <Badge variant="light" size="sm">
                Success Rate
              </Badge>
            </Group>
            <Stack gap="md">
              {attemptBreakdown.map((item) => (
                <div key={item.channel}>
                  <Group justify="space-between" mb="xs">
                    <Group gap="xs">
                      <div
                        style={{
                          width: 8,
                          height: 8,
                          borderRadius: 4,
                          background: item.color,
                        }}
                      />
                      <Text size="sm" fw={500}>
                        {item.channel}
                      </Text>
                    </Group>
                    <Group gap="md">
                      <Text size="xs" c="dimmed">
                        {formatNumber(item.attempts)}
                      </Text>
                      <Badge size="sm" variant="light" color="green">
                        {item.success}%
                      </Badge>
                    </Group>
                  </Group>
                  <Progress value={item.success} color={item.color} size="sm" radius="xl" />
                </div>
              ))}
            </Stack>
          </Card>
        </Grid.Col>

        <Grid.Col span={{ base: 12, lg: 7 }}>
          <Card className="te-command-chart-card">
            <Group justify="space-between" mb="md">
              <Text size="sm" fw={600}>
                Promise to Pay Metrics
              </Text>
              <Group gap="xs">
                <Badge variant="light" color="blue" size="sm">
                  Given: {formatNumber(operationsData.ptpGiven)}
                </Badge>
                <Badge variant="light" color="green" size="sm">
                  Rate: {operationsData.ptpRate}%
                </Badge>
              </Group>
            </Group>
            <div style={{ height: 240 }}>
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={ptpTrendData}>
                  <CartesianGrid strokeDasharray="3 3" stroke={CHART_THEME.grid} />
                  <XAxis dataKey="day" tick={CHART_AXIS_TICK} axisLine={CHART_AXIS_LINE} tickLine={CHART_AXIS_LINE} />
                  <YAxis tick={CHART_AXIS_TICK} axisLine={CHART_AXIS_LINE} tickLine={CHART_AXIS_LINE} />
                  <RechartsTooltip
                    contentStyle={CHART_TOOLTIP_STYLE}
                    labelStyle={CHART_TOOLTIP_TEXT_STYLE}
                    itemStyle={CHART_TOOLTIP_TEXT_STYLE}
                  />
                  <Legend />
                  <Bar dataKey="given" name="PTP Given" fill={COLORS.primary} radius={[4, 4, 0, 0]} />
                  <Bar dataKey="fulfilled" name="Fulfilled" fill={COLORS.success} radius={[4, 4, 0, 0]} />
                  <Bar dataKey="broken" name="Broken" fill={COLORS.danger} radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
            <SimpleGrid cols={3} mt="md">
              <Paper p="sm" radius="md" style={{ ...CHART_SUBTLE_PANEL_STYLE, background: COLORS.primaryLight }}>
                <Text size="xs" c="dimmed">
                  PTP Rate
                </Text>
                <Text size="lg" fw={700} c={COLORS.primary}>
                  {operationsData.ptpRate}%
                </Text>
              </Paper>
              <Paper p="sm" radius="md" style={{ ...CHART_SUBTLE_PANEL_STYLE, background: COLORS.successLight }}>
                <Text size="xs" c="dimmed">
                  Fulfillment
                </Text>
                <Text size="lg" fw={700} c={COLORS.success}>
                  {operationsData.ptpFulfilled}%
                </Text>
              </Paper>
              <Paper p="sm" radius="md" style={{ ...CHART_SUBTLE_PANEL_STYLE, background: COLORS.dangerLight }}>
                <Text size="xs" c="dimmed">
                  Broken
                </Text>
                <Text size="lg" fw={700} c={COLORS.danger}>
                  {operationsData.ptpBroken}%
                </Text>
              </Paper>
            </SimpleGrid>
          </Card>
        </Grid.Col>
      </Grid>
    </Card>
  );
}

function AIDecisionIntelligenceSection() {
  const riskSegmentation = [
    { segment: "Low Risk", count: 520000, percentage: 41.6, color: RISK_COLORS.low },
    { segment: "Medium Risk", count: 380000, percentage: 30.4, color: RISK_COLORS.medium },
    { segment: "High Risk", count: 250000, percentage: 20.0, color: RISK_COLORS.high },
    { segment: "Severe Risk", count: 100000, percentage: 8.0, color: RISK_COLORS.severe },
  ];

  const recoveryProbability = [
    { range: "80-100%", count: 125000, color: "#16a34a" },
    { range: "60-80%", count: 185000, color: "#22c55e" },
    { range: "40-60%", count: 220000, color: "#eab308" },
    { range: "20-40%", count: 180000, color: "#f97316" },
    { range: "0-20%", count: 140000, color: "#ef4444" },
  ];

  const aiStrategies = [
    { strategy: "Call Tonight", cases: 45000, confidence: 87, icon: Phone },
    { strategy: "Offer Settlement", cases: 32000, confidence: 82, icon: Scale },
    { strategy: "Schedule Field Visit", cases: 28000, confidence: 79, icon: MapPin },
    { strategy: "Send Reminder", cases: 65000, confidence: 91, icon: Send },
    { strategy: "Escalate to Legal", cases: 12000, confidence: 74, icon: Landmark },
  ];

  const forecastData = [
    { period: "Next 30 Days", amount: 4500, confidence: 85 },
    { period: "Next 60 Days", amount: 8200, confidence: 78 },
    { period: "Next 90 Days", amount: 11500, confidence: 72 },
  ];

  const intentData = [
    { intent: "Willing to Pay", count: 285000, percentage: 34.2, color: COLORS.success },
    { intent: "Avoiding Contact", count: 180000, percentage: 21.6, color: COLORS.warning },
    { intent: "Financial Hardship", count: 245000, percentage: 29.4, color: COLORS.info },
    { intent: "Disputing Loan", count: 123000, percentage: 14.8, color: COLORS.danger },
  ];

  return (
    <Card className="te-command-section">
      <SectionHeader
        title="AI Decision Intelligence"
        subtitle="Predictive insights and recommended actions powered by AI"
        icon={<Brain size={20} />}
        badge="AI Powered"
        badgeColor="violet"
      />

      <Grid>
        <Grid.Col span={{ base: 12, lg: 6 }}>
          <Card className="te-command-chart-card">
            <Group justify="space-between" mb="md">
              <Text size="sm" fw={600}>
                Borrower Risk Segmentation
              </Text>
              <Badge variant="light" color="violet" size="sm">
                AI Scored
              </Badge>
            </Group>
            <div style={{ height: 220 }}>
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={riskSegmentation}
                    cx="50%"
                    cy="50%"
                    innerRadius={60}
                    outerRadius={90}
                    paddingAngle={2}
                    dataKey="count"
                  >
                    {riskSegmentation.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={entry.color} />
                    ))}
                  </Pie>
                  <RechartsTooltip
                    contentStyle={CHART_TOOLTIP_STYLE}
                    labelStyle={CHART_TOOLTIP_TEXT_STYLE}
                    itemStyle={CHART_TOOLTIP_TEXT_STYLE}
                    formatter={(value) => [formatNumber(Number(value)), "Borrowers"]}
                  />
                </PieChart>
              </ResponsiveContainer>
            </div>
            <SimpleGrid cols={4} mt="sm">
              {riskSegmentation.map((item) => (
                <div key={item.segment} style={{ textAlign: "center" }}>
                  <div
                    style={{
                      width: 12,
                      height: 12,
                      borderRadius: 6,
                      background: item.color,
                      margin: "0 auto 4px",
                    }}
                  />
                  <Text size="xs" c="dimmed">
                    {item.segment}
                  </Text>
                  <Text size="sm" fw={600}>
                    {item.percentage}%
                  </Text>
                </div>
              ))}
            </SimpleGrid>
          </Card>
        </Grid.Col>

        <Grid.Col span={{ base: 12, lg: 6 }}>
          <Card className="te-command-chart-card">
            <Group justify="space-between" mb="md">
              <Text size="sm" fw={600}>
                Recovery Probability Distribution
              </Text>
              <Badge variant="light" color="violet" size="sm">
                ML Model
              </Badge>
            </Group>
            <div style={{ height: 220 }}>
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={recoveryProbability}>
                  <CartesianGrid strokeDasharray="3 3" stroke={CHART_THEME.grid} />
                  <XAxis dataKey="range" tick={CHART_AXIS_TICK_SMALL} axisLine={CHART_AXIS_LINE} tickLine={CHART_AXIS_LINE} />
                  <YAxis tick={CHART_AXIS_TICK} axisLine={CHART_AXIS_LINE} tickLine={CHART_AXIS_LINE} />
                  <RechartsTooltip
                    contentStyle={CHART_TOOLTIP_STYLE}
                    labelStyle={CHART_TOOLTIP_TEXT_STYLE}
                    itemStyle={CHART_TOOLTIP_TEXT_STYLE}
                    formatter={(value) => [formatNumber(Number(value)), "Accounts"]}
                  />
                  <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                    {recoveryProbability.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={entry.color} />
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
                AI Recommended Collection Strategy
              </Text>
              <Badge variant="light" color="violet" size="sm">
                Action Queue
              </Badge>
            </Group>
            <Stack gap="sm">
              {aiStrategies.map((item) => {
                const Icon = item.icon;
                return (
                  <Paper
                    key={item.strategy}
                    p="sm"
                    radius="md"
                    style={{
                      background: COLORS.purpleLight,
                      border: "1px solid rgba(124, 58, 237, 0.15)",
                    }}
                  >
                    <Group justify="space-between">
                      <Group gap="sm">
                        <ThemeIcon size="md" variant="light" color="violet" radius="md">
                          <Icon size={16} />
                        </ThemeIcon>
                        <div>
                          <Text size="sm" fw={500}>
                            {item.strategy}
                          </Text>
                          <Text size="xs" c="dimmed">
                            {formatNumber(item.cases)} cases recommended
                          </Text>
                        </div>
                      </Group>
                      <Badge variant="filled" color="violet" size="sm">
                        {item.confidence}% confidence
                      </Badge>
                    </Group>
                  </Paper>
                );
              })}
            </Stack>
          </Card>
        </Grid.Col>

        <Grid.Col span={{ base: 12, lg: 5 }}>
          <Stack gap="md">
            <Card className="te-command-chart-card">
              <Group justify="space-between" mb="md">
                <Text size="sm" fw={600}>
                  AI Recovery Forecast
                </Text>
                <Badge variant="light" color="violet" size="sm">
                  ₹ in Cr
                </Badge>
              </Group>
              <Stack gap="sm">
                {forecastData.map((item) => (
                  <Paper
                    key={item.period}
                    p="sm"
                    radius="md"
                    style={CHART_SUBTLE_PANEL_STYLE}
                  >
                    <Group justify="space-between">
                      <div>
                        <Text size="sm" fw={500}>
                          {item.period}
                        </Text>
                        <Text size="xs" c="dimmed">
                          {item.confidence}% confidence
                        </Text>
                      </div>
                      <Title order={3} c={COLORS.purple}>
                        ₹{item.amount}Cr
                      </Title>
                    </Group>
                  </Paper>
                ))}
              </Stack>
            </Card>

            <Card className="te-command-chart-card">
              <Group justify="space-between" mb="md">
                <Text size="sm" fw={600}>
                  Borrower Intent Detection
                </Text>
                <Badge variant="light" color="violet" size="sm">
                  NLP Analysis
                </Badge>
              </Group>
              <Stack gap="xs">
                {intentData.map((item) => (
                  <Group key={item.intent} justify="space-between">
                    <Group gap="xs">
                      <div
                        style={{
                          width: 8,
                          height: 8,
                          borderRadius: 4,
                          background: item.color,
                        }}
                      />
                      <Text size="sm">{item.intent}</Text>
                    </Group>
                    <Text size="sm" fw={600}>
                      {item.percentage}%
                    </Text>
                  </Group>
                ))}
              </Stack>
            </Card>
          </Stack>
        </Grid.Col>
      </Grid>
    </Card>
  );
}

function ActionInterventionSection() {
  const highPriorityCases = [
    {
      id: "LN-2024-001245",
      name: "Rajesh Kumar",
      amount: 850000,
      dpd: 75,
      probability: 82,
      region: "Mumbai",
    },
    {
      id: "LN-2024-001892",
      name: "Priya Sharma",
      amount: 620000,
      dpd: 68,
      probability: 78,
      region: "Delhi",
    },
    {
      id: "LN-2024-002156",
      name: "Amit Patel",
      amount: 1200000,
      dpd: 82,
      probability: 75,
      region: "Ahmedabad",
    },
    {
      id: "LN-2024-002489",
      name: "Sunita Reddy",
      amount: 480000,
      dpd: 71,
      probability: 85,
      region: "Hyderabad",
    },
  ];

  const immediateActions = [
    { action: "Broken PTP Today", count: 1245, priority: "critical", icon: AlertTriangle },
    { action: "Legal Notice Due", count: 328, priority: "high", icon: Scale },
    { action: "High-Value Overdue", count: 567, priority: "high", icon: Wallet },
    { action: "Callback Scheduled", count: 2890, priority: "medium", icon: Phone },
  ];

  const settlementRecommendations = [
    { loanId: "LN-2024-003421", principal: 450000, recommended: 315000, savings: 30 },
    { loanId: "LN-2024-003567", principal: 280000, recommended: 210000, savings: 25 },
    { loanId: "LN-2024-003789", principal: 620000, recommended: 403000, savings: 35 },
  ];

  const aiAlerts = [
    {
      message: "PAR 60 increased 8% in Maharashtra region",
      type: "warning",
      time: "2 hours ago",
    },
    {
      message: "Borrowers contacted after 7 PM show 40% higher payment conversion",
      type: "insight",
      time: "4 hours ago",
    },
    {
      message: "Agents in Delhi recovered 3× more via field visits",
      type: "success",
      time: "6 hours ago",
    },
    {
      message: "Settlement acceptance rate dropped 12% in Q4",
      type: "warning",
      time: "1 day ago",
    },
  ];

  return (
    <Card className="te-command-section">
      <SectionHeader
        title="Action & Intervention Panel"
        subtitle="Immediate actions and AI-powered recommendations"
        icon={<Zap size={20} />}
        badge="Action Center"
        badgeColor="orange"
      />

      <Grid>
        <Grid.Col span={{ base: 12, lg: 6 }}>
          <Card className="te-command-chart-card">
            <Group justify="space-between" mb="md">
              <Text size="sm" fw={600}>
                High Priority Cases
              </Text>
              <Badge variant="light" color="red" size="sm">
                {highPriorityCases.length} Cases
              </Badge>
            </Group>
            <ScrollArea style={{ height: 280 }}>
              <Stack gap="sm">
                {highPriorityCases.map((item) => (
                  <Paper
                    key={item.id}
                    p="sm"
                    radius="md"
                    style={{
                      background: "linear-gradient(135deg, rgba(239, 68, 68, 0.06), rgba(239, 68, 68, 0.02))",
                      border: "1px solid rgba(239, 68, 68, 0.15)",
                    }}
                  >
                    <Group justify="space-between" mb="xs">
                      <Group gap="xs">
                        <Text size="sm" fw={600}>
                          {item.name}
                        </Text>
                        <Badge size="xs" variant="light">
                          {item.id}
                        </Badge>
                      </Group>
                      <Badge color="green" size="sm">
                        {item.probability}% recovery
                      </Badge>
                    </Group>
                    <Group justify="space-between">
                      <Group gap="lg">
                        <div>
                          <Text size="xs" c="dimmed">
                            Amount
                          </Text>
                          <Text size="sm" fw={600}>
                            {rupees(item.amount)}
                          </Text>
                        </div>
                        <div>
                          <Text size="xs" c="dimmed">
                            DPD
                          </Text>
                          <Text size="sm" fw={600} c="red">
                            {item.dpd} days
                          </Text>
                        </div>
                        <div>
                          <Text size="xs" c="dimmed">
                            Region
                          </Text>
                          <Text size="sm">{item.region}</Text>
                        </div>
                      </Group>
                      <ActionIcon variant="light" color="blue" radius="md">
                        <ArrowUpRight size={16} />
                      </ActionIcon>
                    </Group>
                  </Paper>
                ))}
              </Stack>
            </ScrollArea>
          </Card>
        </Grid.Col>

        <Grid.Col span={{ base: 12, lg: 6 }}>
          <Card className="te-command-chart-card">
            <Group justify="space-between" mb="md">
              <Text size="sm" fw={600}>
                Immediate Action Queue
              </Text>
              <Badge variant="light" color="orange" size="sm">
                Today
              </Badge>
            </Group>
            <Stack gap="sm">
              {immediateActions.map((item) => {
                const Icon = item.icon;
                const colorMap = {
                  critical: { bg: COLORS.dangerLight, border: "rgba(205, 63, 70, 0.2)", text: COLORS.danger },
                  high: { bg: COLORS.warningLight, border: "rgba(184, 120, 32, 0.2)", text: COLORS.warning },
                  medium: { bg: COLORS.infoLight, border: "rgba(22, 130, 216, 0.2)", text: COLORS.info },
                };
                const colors = colorMap[item.priority as keyof typeof colorMap];
                return (
                  <Paper
                    key={item.action}
                    p="sm"
                    radius="md"
                    style={{
                      background: colors.bg,
                      border: `1px solid ${colors.border}`,
                    }}
                  >
                    <Group justify="space-between">
                      <Group gap="sm">
                        <ThemeIcon
                          size="md"
                          variant="light"
                          color={item.priority === "critical" ? "red" : item.priority === "high" ? "orange" : "blue"}
                          radius="md"
                        >
                          <Icon size={16} />
                        </ThemeIcon>
                        <div>
                          <Text size="sm" fw={500}>
                            {item.action}
                          </Text>
                          <Text size="xs" c="dimmed">
                            Requires immediate attention
                          </Text>
                        </div>
                      </Group>
                      <Badge
                        size="lg"
                        variant="filled"
                        color={item.priority === "critical" ? "red" : item.priority === "high" ? "orange" : "blue"}
                      >
                        {formatNumber(item.count)}
                      </Badge>
                    </Group>
                  </Paper>
                );
              })}
            </Stack>
          </Card>
        </Grid.Col>

        <Grid.Col span={{ base: 12, lg: 6 }}>
          <Card className="te-command-chart-card">
            <Group justify="space-between" mb="md">
              <Text size="sm" fw={600}>
                Settlement Recommendations
              </Text>
              <Badge variant="light" color="teal" size="sm">
                AI Suggested
              </Badge>
            </Group>
            <ScrollArea>
              <Table>
                <Table.Thead>
                  <Table.Tr>
                    <Table.Th>Loan ID</Table.Th>
                    <Table.Th>Principal</Table.Th>
                    <Table.Th>Recommended</Table.Th>
                    <Table.Th>Savings</Table.Th>
                  </Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {settlementRecommendations.map((item) => (
                    <Table.Tr key={item.loanId}>
                      <Table.Td>
                        <Text size="sm" fw={500}>
                          {item.loanId}
                        </Text>
                      </Table.Td>
                      <Table.Td>{rupees(item.principal)}</Table.Td>
                      <Table.Td>
                        <Text fw={600} c={COLORS.teal}>
                          {rupees(item.recommended)}
                        </Text>
                      </Table.Td>
                      <Table.Td>
                        <Badge color="green" variant="light">
                          {item.savings}% off
                        </Badge>
                      </Table.Td>
                    </Table.Tr>
                  ))}
                </Table.Tbody>
              </Table>
            </ScrollArea>
          </Card>
        </Grid.Col>

        <Grid.Col span={{ base: 12, lg: 6 }}>
          <Card className="te-command-chart-card">
            <Group justify="space-between" mb="md">
              <Text size="sm" fw={600}>
                AI Alerts & Intelligence
              </Text>
              <Badge variant="light" color="violet" size="sm">
                Real-time
              </Badge>
            </Group>
            <Stack gap="sm">
              {aiAlerts.map((alert, index) => (
                <Paper
                  key={index}
                  p="sm"
                  radius="md"
                  style={{
                    background:
                      alert.type === "warning"
                        ? COLORS.warningLight
                        : alert.type === "success"
                        ? COLORS.successLight
                        : COLORS.purpleLight,
                    border: `1px solid ${
                      alert.type === "warning"
                        ? "rgba(184, 120, 32, 0.2)"
                        : alert.type === "success"
                        ? "rgba(31, 143, 90, 0.2)"
                        : "rgba(124, 58, 237, 0.15)"
                    }`,
                  }}
                >
                  <Group justify="space-between" align="flex-start">
                    <Group gap="sm" align="flex-start">
                      <ThemeIcon
                        size="sm"
                        variant="light"
                        color={alert.type === "warning" ? "orange" : alert.type === "success" ? "green" : "violet"}
                        radius="md"
                        mt={2}
                      >
                        {alert.type === "warning" ? (
                          <AlertTriangle size={14} />
                        ) : alert.type === "success" ? (
                          <TrendingUp size={14} />
                        ) : (
                          <Brain size={14} />
                        )}
                      </ThemeIcon>
                      <Text size="sm">{alert.message}</Text>
                    </Group>
                    <Text size="xs" c="dimmed" style={{ whiteSpace: "nowrap" }}>
                      {alert.time}
                    </Text>
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
  const [region, setRegion] = useState("");
  const [portfolio, setPortfolio] = useState("");
  const [bucket, setBucket] = useState("");

  return (
    <Stack gap="md" className="te-command-center">
      <ModuleHeader
        title="AI Collections Command Center"
        subtitle="Central operational intelligence for collections management, risk monitoring, and AI-powered recovery insights"
        badge="Mission Control"
        action={
          <Group gap="sm">
            <Menu shadow="md" width={200}>
              <Menu.Target>
                <Button variant="light" leftSection={<Download size={16} />} rightSection={<ChevronDown size={14} />}>
                  Export
                </Button>
              </Menu.Target>
              <Menu.Dropdown>
                <Menu.Label>Export Options</Menu.Label>
                <Menu.Item leftSection={<FileSpreadsheet size={14} />}>Export to Excel</Menu.Item>
                <Menu.Item leftSection={<Download size={14} />}>Export to PDF</Menu.Item>
                <Menu.Divider />
                <Menu.Item leftSection={<Calendar size={14} />}>Schedule Report</Menu.Item>
              </Menu.Dropdown>
            </Menu>
            <Badge variant="filled" color="green" size="lg">
              Live Data
            </Badge>
          </Group>
        }
      />

      <GlobalFilters
        dateRange={dateRange}
        setDateRange={setDateRange}
        region={region}
        setRegion={setRegion}
        portfolio={portfolio}
        setPortfolio={setPortfolio}
        bucket={bucket}
        setBucket={setBucket}
      />

      <PortfolioHealthSection />
      <DelinquencyRiskSection />
      <RecoveryPerformanceSection />
      <CollectionsOperationsSection />
      <AIDecisionIntelligenceSection />
      <ActionInterventionSection />
    </Stack>
  );
}
