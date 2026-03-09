import { Badge, Card, Grid, Group, Loader, Progress, RingProgress, Select, SimpleGrid, Stack, Text, ThemeIcon, Title } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { ChartNoAxesCombined, HandCoins, LoaderCircle, Radar, ShieldAlert, ShieldCheck, Siren, TrendingUp } from "lucide-react";
import { useMemo, useState } from "react";

import { apiFetch, toQuery } from "../../api/client";
import { ModuleHeader } from "../../components/ModuleHeader";
import type { BuildInfo, CampaignRow } from "../../types/api";
import "./overview.css";

interface MetricsResponse {
  bucket_heatmap?: Record<string, number>;
  expected_recovery_amount?: number;
  followup_discipline_rate_pct?: number;
  ptp_miss_count?: number;
  ptp_miss_open_alerts?: number;
  profanity_incidents?: number;
  sla_breaches?: number;
  ptp_rate_by_bucket?: Record<string, { total: number; ptp: number; rate: number }>;
}

interface RollForwardResponse {
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
  total_recovered: number;
  portfolio_value: number;
  recovery_rate_pct: number;
  window_days: number;
}

type Tone = "teal" | "blue" | "orange" | "red";

interface BucketInsight {
  bucket: string;
  exposure: number;
  share: number;
  ptpRate: number;
  tone: Tone;
  detail: string;
}

interface SignalCardProps {
  title: string;
  value: string;
  detail: string;
  tone: Tone;
  progress: number;
  icon: React.ReactNode;
}

const BUCKETS = ["1-30", "31-60", "61-90", "90+"] as const;

const BUCKET_META: Record<(typeof BUCKETS)[number], { tone: Tone; detail: string }> = {
  "1-30": {
    tone: "teal",
    detail: "Fresh delinquency where early containment prevents later migration.",
  },
  "31-60": {
    tone: "blue",
    detail: "Mid-bucket exposure where recoverability remains meaningful but deterioration risk is building.",
  },
  "61-90": {
    tone: "orange",
    detail: "Heavy-risk lane where weak follow-through starts showing up as roll-forward pressure.",
  },
  "90+": {
    tone: "red",
    detail: "Critical exposure that defines tail risk and likely needs escalation or strategy change.",
  },
};

function clamp(value: number, min = 0, max = 100): number {
  return Math.min(max, Math.max(min, value));
}

function rupees(value: number): string {
  try {
    return new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 }).format(value || 0);
  } catch {
    return `INR ${Math.round(value || 0)}`;
  }
}

function percent(value?: number | null): string {
  return `${Number(value || 0).toFixed(1)}%`;
}

function compactCount(value: number): string {
  return new Intl.NumberFormat("en-IN", { notation: "compact", maximumFractionDigits: 1 }).format(value || 0);
}

function points(value: number): string {
  return `${value.toFixed(1)} pts`;
}

function toneForPressure(score: number): { label: string; tone: Tone; detail: string } {
  if (score >= 76) {
    return {
      label: "Intervention",
      tone: "red",
      detail: "The book is carrying too much deterioration pressure for passive monitoring. Strategy change is justified.",
    };
  }
  if (score >= 56) {
    return {
      label: "Tight",
      tone: "orange",
      detail: "The portfolio is still manageable, but concentration and exception pressure are beginning to dominate.",
    };
  }
  if (score >= 31) {
    return {
      label: "Watch",
      tone: "blue",
      detail: "Risk is controlled for now, but the next movement window could change the posture quickly.",
    };
  }
  return {
    label: "Stable",
    tone: "teal",
    detail: "Transition and exception signals are within acceptable guardrails for the current scope.",
  };
}

function signalTone(condition: boolean, fallback: Tone): Tone {
  return condition ? "red" : fallback;
}

function SignalCard({ title, value, detail, tone, progress, icon }: SignalCardProps) {
  return (
    <Card className={`te-overview-signal-card te-overview-signal-card--${tone}`}>
      <Stack gap="sm">
        <Group justify="space-between" align="flex-start">
          <ThemeIcon radius="xl" size={38} color={tone} variant="light">
            {icon}
          </ThemeIcon>
          <Badge variant="light" color={tone}>
            {title}
          </Badge>
        </Group>
        <div>
          <Title order={3} className="te-overview-signal-value">
            {value}
          </Title>
          <Text size="sm" c="dimmed" mt={4}>
            {detail}
          </Text>
        </div>
        <Progress value={clamp(progress)} color={tone} radius="xl" size="md" />
      </Stack>
    </Card>
  );
}

export function RiskPortfolioPage() {
  const [campaignId, setCampaignId] = useState("");

  const metrics = useQuery({
    queryKey: ["metrics", campaignId],
    queryFn: () => apiFetch<MetricsResponse>(`/api/metrics${toQuery({ campaign_id: campaignId })}`),
  });
  const campaigns = useQuery({ queryKey: ["campaigns"], queryFn: () => apiFetch<{ rows: CampaignRow[] }>("/api/campaigns") });
  const build = useQuery({ queryKey: ["build_info"], queryFn: () => apiFetch<BuildInfo>("/api/system/build_info") });
  const rollForward = useQuery({
    queryKey: ["metrics_roll_forward", campaignId],
    queryFn: () => apiFetch<RollForwardResponse>(`/api/metrics/roll-forward${toQuery({ campaign_id: campaignId, days: 30 })}`),
  });
  const recovery = useQuery({
    queryKey: ["metrics_recovery", campaignId],
    queryFn: () => apiFetch<RecoveryResponse>(`/api/metrics/recovery${toQuery({ campaign_id: campaignId, days: 30 })}`),
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
  const portfolioValue = Number(recovery.data?.portfolio_value || 0);
  const realizedRecoveryRate = Number(recovery.data?.recovery_rate_pct || 0);
  const expectedRecoveryAmount = Number(m.expected_recovery_amount || 0);
  const expectedRecoveryRate = portfolioValue > 0 ? (expectedRecoveryAmount / portfolioValue) * 100 : 0;
  const recoveryGapRate = Math.max(0, expectedRecoveryRate - realizedRecoveryRate);

  const totalBucketExposure = BUCKETS.reduce((sum, bucket) => sum + Number(m.bucket_heatmap?.[bucket] || 0), 0);
  const bucketInsights: BucketInsight[] = BUCKETS.map((bucket) => {
    const exposure = Number(m.bucket_heatmap?.[bucket] || 0);
    const ptpRate = Number(m.ptp_rate_by_bucket?.[bucket]?.rate || 0);
    return {
      bucket,
      exposure,
      share: totalBucketExposure > 0 ? (exposure / totalBucketExposure) * 100 : 0,
      ptpRate,
      tone: BUCKET_META[bucket].tone,
      detail: BUCKET_META[bucket].detail,
    };
  });

  const totalExposure = bucketInsights.reduce((sum, item) => sum + item.exposure, 0);
  const highRiskExposure = bucketInsights.filter((item) => item.bucket === "61-90" || item.bucket === "90+").reduce((sum, item) => sum + item.exposure, 0);
  const criticalExposure = bucketInsights.find((item) => item.bucket === "90+")?.exposure || 0;
  const highRiskShare = totalExposure > 0 ? (highRiskExposure / totalExposure) * 100 : 0;
  const topBucket = [...bucketInsights].sort((a, b) => b.exposure - a.exposure)[0];
  const strongestBucket = [...bucketInsights]
    .filter((item) => item.exposure > 0 || item.ptpRate > 0)
    .sort((a, b) => b.ptpRate - a.ptpRate)[0];
  const weakestBucket = [...bucketInsights]
    .filter((item) => item.exposure > 0 || item.ptpRate > 0)
    .sort((a, b) => a.ptpRate - b.ptpRate)[0];

  const followupDiscipline = Number(m.followup_discipline_rate_pct || 0);
  const rollForwardRate = Number(rollForward.data?.roll_forward_pct || 0);
  const rollbackRate = Number(rollForward.data?.rollback_pct || 0);
  const cureRate = Number(rollForward.data?.cure_rate_pct || 0);
  const containmentRate =
    rollForward.data && rollForward.data.total_transitions > 0 ? 100 - Number(rollForward.data.roll_forward_pct || 0) : null;
  const openMissedPtp = Number(m.ptp_miss_open_alerts || 0);
  const slaBreaches = Number(m.sla_breaches || 0);
  const profanityIncidents = Number(m.profanity_incidents || 0);
  const exceptionCount = openMissedPtp + slaBreaches + profanityIncidents;
  const pressureIndex = Math.round(
    clamp(
      highRiskShare * 0.45 +
        clamp(100 - followupDiscipline) * 0.23 +
        clamp(100 - (containmentRate == null ? 72 : containmentRate)) * 0.17 +
        Math.min(16, openMissedPtp * 4) +
        Math.min(12, slaBreaches * 2.5) +
        Math.min(8, profanityIncidents * 2),
    ),
  );
  const pressure = toneForPressure(pressureIndex);

  const transitionWindow = Number(rollForward.data?.window_days || 30);
  const recoveryWindow = Number(recovery.data?.window_days || 30);
  const transitionRead =
    Number(rollForward.data?.total_transitions || 0) === 0
      ? "Transition pressure will become clearer once DPD movement starts accumulating."
      : rollForwardRate > rollbackRate && rollForwardRate > cureRate
        ? "More accounts are worsening than improving. Containment is not yet offsetting deterioration."
        : cureRate >= rollForwardRate
          ? "Cures are keeping pace with or exceeding deterioration. The book is showing early signs of stabilization."
          : "The portfolio is mixed. Some improvement is visible, but not enough to call the movement profile healthy.";

  const narrative = selectedCampaign
    ? `${selectedCampaign.name} currently has ${percent(highRiskShare)} of scoped accounts in 61+ DPD. Roll-forward rate is ${percent(
        rollForwardRate,
      )}, cure rate is ${percent(cureRate)}, and ${exceptionCount} portfolio exceptions are still open.`
    : `${campaigns.data?.rows.length || 0} campaigns are in scope. ${topBucket ? topBucket.bucket : "31-60"} holds the largest current exposure, while ${
        strongestBucket ? strongestBucket.bucket : "1-30"
      } is the strongest recovery lane right now.`;

  const heroHighlights = [
    {
      label: "Scope value",
      value: rupees(portfolioValue),
      detail: selectedCampaign ? "Current campaign exposure in view" : "Portfolio value across the scoped book",
    },
    {
      label: "Expected recovery",
      value: rupees(expectedRecoveryAmount),
      detail: `${percent(expectedRecoveryRate)} of scoped value is currently backed by active commitments`,
    },
    {
      label: "61+ DPD share",
      value: percent(highRiskShare),
      detail: `${compactCount(highRiskExposure)} accounts already sit in high-risk buckets`,
    },
    {
      label: "Open exceptions",
      value: compactCount(exceptionCount),
      detail: `${openMissedPtp} missed PTP, ${slaBreaches} SLA breaches, ${profanityIncidents} conduct incidents`,
    },
  ];

  const signals: SignalCardProps[] = [
    {
      title: "Portfolio At Risk",
      value: `${compactCount(highRiskExposure)} accts`,
      detail: `${percent(highRiskShare)} of the scoped book sits in 61+ DPD. ${compactCount(criticalExposure)} accounts are already 90+.`,
      tone: signalTone(highRiskShare >= 40, highRiskShare >= 24 ? "orange" : "teal"),
      progress: highRiskShare,
      icon: <Radar size={18} />,
    },
    {
      title: "Transition Pressure",
      value: percent(rollForwardRate),
      detail: `${Number(rollForward.data?.roll_forward_count || 0)} worsening transitions inside a ${transitionWindow}-day window.`,
      tone: signalTone(rollForwardRate >= 25, rollForwardRate >= 15 ? "orange" : "blue"),
      progress: rollForwardRate,
      icon: <ShieldAlert size={18} />,
    },
    {
      title: "Cure Rate",
      value: percent(cureRate),
      detail: `${Number(rollForward.data?.cure_count || 0)} accounts cured to current across ${Number(rollForward.data?.total_transitions || 0)} tracked transitions.`,
      tone: cureRate >= 20 ? "teal" : cureRate >= 10 ? "blue" : "orange",
      progress: cureRate,
      icon: <ShieldCheck size={18} />,
    },
    {
      title: "Recoverability",
      value: percent(expectedRecoveryRate),
      detail: `${rupees(expectedRecoveryAmount)} expected versus ${percent(realizedRecoveryRate)} realized over ${recoveryWindow} days.`,
      tone: expectedRecoveryRate >= 10 ? "teal" : expectedRecoveryRate >= 5 ? "blue" : "orange",
      progress: expectedRecoveryRate,
      icon: <HandCoins size={18} />,
    },
    {
      title: "Exception Load",
      value: compactCount(exceptionCount),
      detail: `${openMissedPtp} missed PTP, ${slaBreaches} SLA breaches, and ${profanityIncidents} profanity incidents remain unresolved.`,
      tone: exceptionCount > 0 ? "red" : "teal",
      progress: Math.min(100, exceptionCount * 12),
      icon: <Siren size={18} />,
    },
  ];

  const attentionBoard = [
    {
      title: "Missed-PTP Pressure",
      value: `${openMissedPtp} open`,
      detail: `${Number(m.ptp_miss_count || 0)} missed commitments have already been processed. The unresolved ones can still feed next-bucket risk.`,
      tone: openMissedPtp > 0 ? "red" : "teal",
      icon: <Siren size={16} />,
    },
    {
      title: "Containment Risk",
      value: containmentRate == null ? "Building" : percent(containmentRate),
      detail:
        containmentRate == null
          ? "Containment posture will appear once enough DPD movement history accumulates."
          : `${Number(rollForward.data?.roll_forward_count || 0)} roll-forwards, ${Number(rollForward.data?.rollback_count || 0)} rollbacks, and ${Number(
              rollForward.data?.cure_count || 0,
            )} cures are currently in the tracked window.`,
      tone: containmentRate != null && containmentRate < 80 ? "orange" : "blue",
      icon: <ShieldAlert size={16} />,
    },
    {
      title: "Recovery Gap",
      value: points(recoveryGapRate),
      detail: `${percent(expectedRecoveryRate)} expected recovery rate versus ${percent(realizedRecoveryRate)} realized recovery rate over ${recoveryWindow} days.`,
      tone: recoveryGapRate > 5 ? "orange" : "teal",
      icon: <HandCoins size={16} />,
    },
    {
      title: "Concentration Risk",
      value: topBucket ? topBucket.bucket : "n/a",
      detail: topBucket
        ? `${percent(topBucket.share)} of scoped exposure is concentrated in ${topBucket.bucket}. ${compactCount(criticalExposure)} accounts are already 90+.`
        : "Bucket concentration will appear once scoped exposures are populated.",
      tone: topBucket?.bucket === "90+" || highRiskShare >= 40 ? "red" : topBucket?.tone || "blue",
      icon: <Radar size={16} />,
    },
  ];

  return (
    <Stack gap="lg">
      <ModuleHeader
        title="Risk / Portfolio Dashboard"
        subtitle="A dedicated collections risk view for reading cure, roll-forward, recoverability, and concentration without duplicating the desk execution dashboard."
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

      <Card className="te-overview-hero">
        <div className="te-overview-hero-grid">
          <Stack gap="md" className="te-overview-hero-copy">
            <div>
              <Text className="te-overview-hero-kicker">Portfolio risk command</Text>
              <Title className="te-overview-hero-title">Read the collections book as exposure, migration, and recoverability.</Title>
              <Text className="te-overview-hero-subtitle">{narrative}</Text>
            </div>

            <Group gap="xs" wrap="wrap">
              <Badge variant="outline" color={pressure.tone}>
                Operating pressure: {pressure.label}
              </Badge>
              <Badge variant="outline" color={topBucket?.tone || "blue"}>
                Largest exposure: {topBucket?.bucket || "n/a"}
              </Badge>
              <Badge variant="outline" color={highRiskShare >= 40 ? "red" : highRiskShare >= 24 ? "orange" : "blue"}>
                High-risk share: {percent(highRiskShare)}
              </Badge>
              <Badge variant="outline" color={exceptionCount > 0 ? "red" : "teal"}>
                Open exceptions: {compactCount(exceptionCount)}
              </Badge>
            </Group>

            <Text size="sm" className="te-overview-hero-detail">
              Pressure index is derived from 61+ DPD concentration, follow-up reliability, containment, and unresolved exception load.
            </Text>
          </Stack>

          <div className="te-overview-hero-aside">
            <Card className="te-overview-pressure-card">
              <Group justify="space-between" align="flex-start" wrap="nowrap">
                <div>
                  <Text className="te-overview-pressure-label">Operating pressure</Text>
                  <Title order={3}>{pressureIndex}/100</Title>
                  <Text size="sm" c="dimmed" mt={4}>
                    {pressure.detail}
                  </Text>
                </div>
                <RingProgress
                  size={150}
                  thickness={16}
                  roundCaps
                  sections={[{ value: pressureIndex, color: pressure.tone }]}
                  label={
                    <Stack gap={0} align="center">
                      <Text fw={700} size="lg">
                        {pressure.label}
                      </Text>
                      <Text size="xs" c="dimmed">
                        Risk posture
                      </Text>
                    </Stack>
                  }
                />
              </Group>
            </Card>

            <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="sm">
              {heroHighlights.map((item) => (
                <Card key={item.label} className="te-overview-mini-card">
                  <Text className="te-overview-mini-label">{item.label}</Text>
                  <Title order={4}>{item.value}</Title>
                  <Text size="xs" c="dimmed" mt={4}>
                    {item.detail}
                  </Text>
                </Card>
              ))}
            </SimpleGrid>
          </div>
        </div>
      </Card>

      <SimpleGrid cols={{ base: 1, md: 2, xl: 5 }}>
        {signals.map((item) => (
          <SignalCard key={item.title} {...item} />
        ))}
      </SimpleGrid>

      <Grid>
        <Grid.Col span={{ base: 12, lg: 7 }}>
          <Card className="te-data-card">
            <Group justify="space-between" mb="md">
              <div>
                <Title order={4}>Portfolio Risk Ladder</Title>
                <Text size="sm" c="dimmed">
                  DPD concentration by lane, including how much of the scoped book each bucket controls and how well each lane is converting.
                </Text>
              </div>
              <Badge variant="outline">Exposure by bucket</Badge>
            </Group>

            <Stack gap="md">
              {bucketInsights.map((bucket) => (
                <Card key={bucket.bucket} className={`te-overview-bucket-card te-overview-bucket-card--${bucket.tone}`}>
                  <Stack gap="xs">
                    <Group justify="space-between" align="center">
                      <Group gap="sm">
                        <ThemeIcon radius="xl" size={34} color={bucket.tone} variant="light">
                          {bucket.bucket === "90+" ? <ShieldAlert size={16} /> : bucket.bucket === "61-90" ? <LoaderCircle size={16} /> : <ChartNoAxesCombined size={16} />}
                        </ThemeIcon>
                        <div>
                          <Text fw={700}>{bucket.bucket} DPD</Text>
                          <Text size="xs" c="dimmed">
                            {bucket.detail}
                          </Text>
                        </div>
                      </Group>
                      <Group gap="xs">
                        <Badge variant="light" color={bucket.tone}>
                          {compactCount(bucket.exposure)} accounts
                        </Badge>
                        <Badge variant="outline" color={bucket.tone}>
                          {percent(bucket.share)}
                        </Badge>
                      </Group>
                    </Group>
                    <Progress value={bucket.share} color={bucket.tone} radius="xl" size="lg" />
                    <Group justify="space-between">
                      <Text size="sm" c="dimmed">
                        Share of scoped portfolio
                      </Text>
                      <Badge variant="dot" color={bucket.tone}>
                        Recovery lane {percent(bucket.ptpRate)}
                      </Badge>
                    </Group>
                  </Stack>
                </Card>
              ))}
            </Stack>
          </Card>
        </Grid.Col>

        <Grid.Col span={{ base: 12, lg: 5 }}>
          <Card className="te-data-card te-overview-attention-card">
            <Group justify="space-between" mb="md">
              <div>
                <Title order={4}>Attention Board</Title>
                <Text size="sm" c="dimmed">
                  The four risk-side explanations a collections head should read before changing strategy or launching an experiment.
                </Text>
              </div>
              <Badge variant="outline" color={pressure.tone}>
                {pressure.label}
              </Badge>
            </Group>

            <Stack gap="sm">
              {attentionBoard.map((item) => (
                <div key={item.title} className={`te-overview-attention-row te-overview-attention-row--${item.tone}`}>
                  <ThemeIcon radius="xl" size={36} color={item.tone} variant="light">
                    {item.icon}
                  </ThemeIcon>
                  <div className="te-overview-attention-copy">
                    <Group justify="space-between" align="center">
                      <Text fw={700}>{item.title}</Text>
                      <Badge variant="light" color={item.tone}>
                        {item.value}
                      </Badge>
                    </Group>
                    <Text size="sm" c="dimmed">
                      {item.detail}
                    </Text>
                  </div>
                </div>
              ))}
            </Stack>
          </Card>
        </Grid.Col>
      </Grid>

      <Grid>
        <Grid.Col span={{ base: 12, lg: 6 }}>
          <Card className="te-data-card">
            <Group justify="space-between" mb="md">
              <div>
                <Title order={4}>Transition Outlook</Title>
                <Text size="sm" c="dimmed">
                  A portfolio-level read of whether the scoped book is curing, rolling forward, or only partially stabilizing.
                </Text>
              </div>
              <Badge variant="outline">{transitionWindow}-day transition view</Badge>
            </Group>

            <SimpleGrid cols={{ base: 1, sm: 2, xl: 4 }} mb="md">
              <Card className="te-overview-stat-card">
                <Text size="sm" c="dimmed">
                  Roll Forward Rate
                </Text>
                <Title order={4}>{percent(rollForwardRate)}</Title>
                <Text size="xs" c="dimmed">
                  Share of tracked transitions that worsened bucket position
                </Text>
              </Card>
              <Card className="te-overview-stat-card">
                <Text size="sm" c="dimmed">
                  Cure Rate
                </Text>
                <Title order={4}>{percent(cureRate)}</Title>
                <Text size="xs" c="dimmed">
                  Accounts that returned fully current from delinquent buckets
                </Text>
              </Card>
              <Card className="te-overview-stat-card">
                <Text size="sm" c="dimmed">
                  Rollback Rate
                </Text>
                <Title order={4}>{percent(rollbackRate)}</Title>
                <Text size="xs" c="dimmed">
                  Accounts that improved to a lower-risk bucket without fully curing
                </Text>
              </Card>
              <Card className="te-overview-stat-card">
                <Text size="sm" c="dimmed">
                  Tracked Transitions
                </Text>
                <Title order={4}>{compactCount(Number(rollForward.data?.total_transitions || 0))}</Title>
                <Text size="xs" c="dimmed">
                  Observed movement events inside the active transition window
                </Text>
              </Card>
            </SimpleGrid>

            <SimpleGrid cols={{ base: 1, md: 2 }} spacing="sm">
              <Card className="te-overview-mini-card">
                <Text className="te-overview-mini-label">Movement read</Text>
                <Title order={5}>Portfolio direction</Title>
                <Text size="sm" c="dimmed" mt={4}>
                  {transitionRead}
                </Text>
              </Card>
              <Card className="te-overview-mini-card">
                <Text className="te-overview-mini-label">Lane watch</Text>
                <Title order={5}>{topBucket ? `${topBucket.bucket} carries the largest weight` : "Awaiting exposure data"}</Title>
                <Text size="sm" c="dimmed" mt={4}>
                  {weakestBucket
                    ? `${weakestBucket.bucket} is the weakest conversion lane at ${percent(weakestBucket.ptpRate)}.`
                    : "Weakest-lane read will appear once bucket-level conversion signals accumulate."}
                </Text>
              </Card>
            </SimpleGrid>
          </Card>
        </Grid.Col>

        <Grid.Col span={{ base: 12, lg: 6 }}>
          <Card className="te-data-card">
            <Group justify="space-between" mb="md">
              <div>
                <Title order={4}>Recovery Outlook</Title>
                <Text size="sm" c="dimmed">
                  Expected recovery, realized recovery, and the remaining gap between commitment-backed value and actual collections performance.
                </Text>
              </div>
              <Badge variant="outline">Portfolio value lens</Badge>
            </Group>

            <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="sm" mb="md">
              <Card className="te-overview-stat-card">
                <Text size="sm" c="dimmed">
                  Scoped Value
                </Text>
                <Title order={4}>{rupees(portfolioValue)}</Title>
                <Text size="xs" c="dimmed">
                  Current scoped portfolio value in this risk view
                </Text>
              </Card>
              <Card className="te-overview-stat-card">
                <Text size="sm" c="dimmed">
                  Expected Recovery
                </Text>
                <Title order={4}>{rupees(expectedRecoveryAmount)}</Title>
                <Text size="xs" c="dimmed">
                  Value currently supported by active borrower commitments
                </Text>
              </Card>
              <Card className="te-overview-stat-card">
                <Text size="sm" c="dimmed">
                  Realized Recovery Rate
                </Text>
                <Title order={4}>{percent(realizedRecoveryRate)}</Title>
                <Text size="xs" c="dimmed">
                  Actual collections performance over the last {recoveryWindow} days
                </Text>
              </Card>
              <Card className="te-overview-stat-card">
                <Text size="sm" c="dimmed">
                  Gap To Expected
                </Text>
                <Title order={4}>{points(recoveryGapRate)}</Title>
                <Text size="xs" c="dimmed">
                  Difference between expected recovery rate and realized recovery rate
                </Text>
              </Card>
            </SimpleGrid>

            <Stack gap="sm">
              <div className={`te-overview-attention-row te-overview-attention-row--${strongestBucket?.tone || "teal"}`}>
                <ThemeIcon radius="xl" size={36} color={strongestBucket?.tone || "teal"} variant="light">
                  <TrendingUp size={16} />
                </ThemeIcon>
                <div className="te-overview-attention-copy">
                  <Group justify="space-between" align="center">
                    <Text fw={700}>Best recovery lane</Text>
                    <Badge variant="light" color={strongestBucket?.tone || "teal"}>
                      {strongestBucket?.bucket || "n/a"}
                    </Badge>
                  </Group>
                  <Text size="sm" c="dimmed">
                    {strongestBucket
                      ? `${percent(strongestBucket.ptpRate)} commitment conversion in the strongest-performing bucket right now.`
                      : "Recovery-lane strength will appear once bucket-level outcomes accumulate."}
                  </Text>
                </div>
              </div>

              <div className={`te-overview-attention-row te-overview-attention-row--${weakestBucket?.tone || "orange"}`}>
                <ThemeIcon radius="xl" size={36} color={weakestBucket?.tone || "orange"} variant="light">
                  <ShieldAlert size={16} />
                </ThemeIcon>
                <div className="te-overview-attention-copy">
                  <Group justify="space-between" align="center">
                    <Text fw={700}>Weakest conversion lane</Text>
                    <Badge variant="light" color={weakestBucket?.tone || "orange"}>
                      {weakestBucket?.bucket || "n/a"}
                    </Badge>
                  </Group>
                  <Text size="sm" c="dimmed">
                    {weakestBucket
                      ? `${percent(weakestBucket.ptpRate)} conversion in the weakest bucket. This is where strategy tightening is most likely to pay off first.`
                      : "Weak-lane diagnostics will appear once scoped conversion data is available."}
                  </Text>
                </div>
              </div>
            </Stack>
          </Card>
        </Grid.Col>
      </Grid>
    </Stack>
  );
}
