import {
  Badge,
  Button,
  Card,
  Divider,
  Grid,
  Group,
  Loader,
  Paper,
  Select,
  SimpleGrid,
  Stack,
  Text,
  Textarea,
  ThemeIcon,
  Title,
} from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { useQuery } from "@tanstack/react-query";
import {
  ArrowRight,
  Bot,
  FlaskConical,
  Radar,
  SendHorizontal,
  ShieldCheck,
  Sparkles,
  TrendingUp,
  TriangleAlert,
  UserRound,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import { apiFetch } from "../../api/client";
import { EmptyStateCard } from "../../components/EmptyStateCard";
import { ModuleHeader } from "../../components/ModuleHeader";
import type { BuildInfo, CampaignRow } from "../../types/api";
import "./control-layer.css";

interface SummaryCard {
  label: string;
  value: string;
  detail: string;
}

interface MetricChip {
  label: string;
  value: string;
}

interface EvidenceCard {
  title: string;
  entity_type: string;
  entity_id?: string;
  summary: string;
  sample_size: number;
  confidence: string;
  metrics: MetricChip[];
}

interface ImpactEstimate {
  summary: string;
  confidence: string;
  basis: string;
  uplift_low_pct?: number;
  uplift_high_pct?: number;
  additional_commitments_low?: number;
  additional_commitments_high?: number;
  recovery_low?: number;
  recovery_high?: number;
}

interface ActionProposal {
  id: string;
  action_type: string;
  cta_label: string;
  approval_mode: string;
  title: string;
  summary: string;
  payload: Record<string, unknown>;
}

interface Recommendation {
  id: string;
  kind: string;
  title: string;
  summary: string;
  rationale: string;
  confidence: string;
  expected_impact: ImpactEstimate;
  actions: ActionProposal[];
}

interface ChatResponse {
  scope: {
    campaign_id?: string | null;
    campaign_name?: string | null;
    scope_label: string;
    campaign_selected: boolean;
  };
  answer: string;
  summary: SummaryCard[];
  evidence: EvidenceCard[];
  recommendations: Recommendation[];
  quick_replies: string[];
  generated_at: number;
}

interface ActionResponse {
  ok: boolean;
  action_type: string;
  result_type: string;
  message: string;
  approval?: { id?: string; status?: string };
  experiment?: { id?: string; name?: string };
}

type Turn =
  | { id: string; role: "user"; message: string }
  | { id: string; role: "assistant"; response: ChatResponse };

const DEFAULT_PROMPT = "What should I change this week?";
const FALLBACK_QUICK_REPLIES = [
  "What is working by bucket right now?",
  "Which agent is outperforming after bucket mix?",
  "Simulate the impact of a strategy change in 31-60 DPD.",
  "What campaign should I focus on first?",
];
const DEFAULT_HERO_SUMMARY: SummaryCard[] = [
  { label: "Grounded read", value: "Campaign to account", detail: "Buckets, agents, customers, follow-up pressure, and containment in one layer." },
  { label: "Decision support", value: "Evidence first", detail: "Every recommendation is tied to sample size, confidence, and visible basis." },
  { label: "Governed execution", value: "Direct or approval", detail: "Run experiments directly or queue operating changes through approvals." },
  { label: "Operator workflow", value: "Chat to action", detail: "Ask, diagnose, simulate, and trigger the next move without switching modules." },
];

function nextId(prefix: string): string {
  return `${prefix}-${Math.random().toString(36).slice(2, 10)}`;
}

function confidenceColor(value?: string): string {
  switch ((value || "").toLowerCase()) {
    case "high":
      return "teal";
    case "medium":
      return "blue";
    default:
      return "gray";
  }
}

function entityIcon(entityType: string) {
  switch (entityType) {
    case "campaign":
      return <TrendingUp size={14} />;
    case "bucket":
      return <TriangleAlert size={14} />;
    case "agent":
      return <UserRound size={14} />;
    default:
      return <Bot size={14} />;
  }
}

function actionResultColor(resultType?: string): string {
  if (resultType === "experiment_created") {
    return "teal";
  }
  if (resultType === "approval_queued") {
    return "blue";
  }
  return "gray";
}

function SummaryTile({ item, inverse = false }: { item: SummaryCard; inverse?: boolean }) {
  return (
    <Card className={inverse ? "te-control-summary-tile te-control-summary-tile--inverse" : "te-control-summary-tile"} withBorder>
      <Text className="te-control-summary-label">{item.label}</Text>
      <Title order={4} className="te-control-summary-value">
        {item.value}
      </Title>
      <Text size="sm" className="te-control-summary-detail">
        {item.detail}
      </Text>
    </Card>
  );
}

function ImpactBand({ impact }: { impact: ImpactEstimate }) {
  return (
    <Paper className="te-control-impact-band" radius="xl" p="md">
      <Stack gap={6}>
        <Group justify="space-between" align="center">
          <Text className="te-control-impact-kicker">Expected impact</Text>
          <Badge variant="light" color={confidenceColor(impact.confidence)}>
            {impact.confidence}
          </Badge>
        </Group>
        <Text className="te-control-impact-summary">{impact.summary}</Text>
        <Text size="xs" className="te-control-impact-basis">
          {impact.basis}
        </Text>
        <Group gap="xs">
          {impact.additional_commitments_low != null ? (
            <Badge variant="outline" className="te-control-metric-pill">
              +{impact.additional_commitments_low} to +{impact.additional_commitments_high} commitments
            </Badge>
          ) : null}
          {impact.recovery_low != null ? (
            <Badge variant="outline" className="te-control-metric-pill">
              INR {impact.recovery_low} to {impact.recovery_high}
            </Badge>
          ) : null}
        </Group>
      </Stack>
    </Paper>
  );
}

function ActionTile({
  action,
  result,
  busy,
  onRun,
}: {
  action: ActionProposal;
  result?: ActionResponse;
  busy: boolean;
  onRun: (action: ActionProposal) => void;
}) {
  const direct = action.approval_mode !== "approval_required";
  return (
    <Card className="te-control-action-tile" withBorder radius="xl" p="md">
      <Stack gap="sm">
        <Group justify="space-between" align="flex-start">
          <div>
            <Text fw={700} size="sm">
              {action.title}
            </Text>
            <Text size="xs" c="dimmed">
              {action.summary}
            </Text>
          </div>
          <Badge variant="outline" color={direct ? "teal" : "orange"}>
            {direct ? "Direct" : "Approval"}
          </Badge>
        </Group>

        <Button
          className={direct ? "te-control-action-button te-control-action-button--primary" : "te-control-action-button te-control-action-button--secondary"}
          onClick={() => onRun(action)}
          loading={busy}
          rightSection={<ArrowRight size={14} />}
          leftSection={action.action_type === "launch_experiment" ? <FlaskConical size={14} /> : <ShieldCheck size={14} />}
        >
          {action.cta_label}
        </Button>

        {result ? (
          <Badge variant="light" color={actionResultColor(result.result_type)} w="fit-content">
            {result.message}
          </Badge>
        ) : null}
      </Stack>
    </Card>
  );
}

function RecommendationCard({
  item,
  actionBusyId,
  actionResults,
  onRun,
}: {
  item: Recommendation;
  actionBusyId: string;
  actionResults: Record<string, ActionResponse>;
  onRun: (action: ActionProposal) => void;
}) {
  return (
    <Card className="te-control-rec-card" withBorder radius="xl" p="lg">
      <Stack gap="md">
        <Group justify="space-between" align="flex-start">
          <div>
            <Text className="te-control-rec-kicker">{item.kind.replaceAll("_", " ")}</Text>
            <Title order={4}>{item.title}</Title>
            <Text size="sm" c="dimmed" mt={6}>
              {item.summary}
            </Text>
          </div>
          <Badge variant="light" color={confidenceColor(item.confidence)}>
            {item.confidence}
          </Badge>
        </Group>

        <Text className="te-control-rec-rationale">{item.rationale}</Text>
        <ImpactBand impact={item.expected_impact} />

        {item.actions.length ? (
          <>
            <Divider />
            <SimpleGrid cols={{ base: 1, md: 2 }}>
              {item.actions.map((action) => (
                <ActionTile
                  key={action.id}
                  action={action}
                  result={actionResults[action.id]}
                  busy={actionBusyId === action.id}
                  onRun={onRun}
                />
              ))}
            </SimpleGrid>
          </>
        ) : null}
      </Stack>
    </Card>
  );
}

function EvidenceTile({ item }: { item: EvidenceCard }) {
  return (
    <Card className="te-control-evidence-card" withBorder radius="xl" p="md">
      <Stack gap="sm">
        <Group justify="space-between" align="flex-start">
          <Group align="flex-start" gap="sm">
            <ThemeIcon className="te-control-evidence-icon" size="lg" radius="xl">
              {entityIcon(item.entity_type)}
            </ThemeIcon>
            <div>
              <Text fw={700}>{item.title}</Text>
              <Text size="sm" c="dimmed">
                {item.summary}
              </Text>
            </div>
          </Group>
          <Badge variant="light" color={confidenceColor(item.confidence)}>
            {item.confidence}
          </Badge>
        </Group>

        <Text size="xs" className="te-control-evidence-sample">
          Sample size {item.sample_size}
        </Text>
        <Group gap="xs">
          {item.metrics.map((metric) => (
            <Badge key={`${item.title}-${metric.label}`} variant="outline" className="te-control-metric-pill">
              {metric.label}: {metric.value}
            </Badge>
          ))}
        </Group>
      </Stack>
    </Card>
  );
}

function AssistantTurn({
  turn,
  actionBusyId,
  actionResults,
  onRun,
}: {
  turn: ChatResponse;
  actionBusyId: string;
  actionResults: Record<string, ActionResponse>;
  onRun: (action: ActionProposal) => void;
}) {
  return (
    <Card className="te-control-turn te-control-turn--assistant" withBorder radius="xl" p="lg">
      <Stack gap="lg">
        <Group justify="space-between" align="flex-start">
          <Group align="flex-start" gap="sm">
            <ThemeIcon className="te-control-turn-avatar" size="xl" radius="xl">
              <Bot size={18} />
            </ThemeIcon>
            <div>
              <Text className="te-control-turn-label">Operations Copilot</Text>
              <Text size="sm" c="dimmed">
                {turn.scope.scope_label}
              </Text>
            </div>
          </Group>
          <Badge variant="outline" color="blue">
            Evidence-backed
          </Badge>
        </Group>

        <Paper className="te-control-answer-panel" radius="xl" p="lg">
          <Stack gap="xs">
            <Text className="te-control-answer-kicker">Control-layer readout</Text>
            <Text className="te-control-answer-copy">{turn.answer}</Text>
          </Stack>
        </Paper>

        {turn.summary.length ? (
          <SimpleGrid cols={{ base: 1, md: 2 }}>
            {turn.summary.map((item) => (
              <SummaryTile key={item.label} item={item} />
            ))}
          </SimpleGrid>
        ) : null}

        {turn.evidence.length ? (
          <Stack gap="sm">
            <Group justify="space-between" align="center">
              <Title order={5}>Evidence blocks</Title>
              <Badge variant="light">{turn.evidence.length}</Badge>
            </Group>
            <SimpleGrid cols={{ base: 1, md: 2 }}>
              {turn.evidence.map((item) => (
                <EvidenceTile key={`${item.entity_type}-${item.entity_id || item.title}`} item={item} />
              ))}
            </SimpleGrid>
          </Stack>
        ) : null}

        {turn.recommendations.length ? (
          <Stack gap="sm">
            <Group justify="space-between" align="center">
              <Title order={5}>Recommended moves</Title>
              <Badge variant="light" color="orange">
                Actionable
              </Badge>
            </Group>
            {turn.recommendations.map((item) => (
              <RecommendationCard
                key={item.id}
                item={item}
                actionBusyId={actionBusyId}
                actionResults={actionResults}
                onRun={onRun}
              />
            ))}
          </Stack>
        ) : null}
      </Stack>
    </Card>
  );
}

export function ControlLayerPage() {
  const [campaignId, setCampaignId] = useState("");
  const [draft, setDraft] = useState("");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [busy, setBusy] = useState(false);
  const [actionBusyId, setActionBusyId] = useState("");
  const [actionResults, setActionResults] = useState<Record<string, ActionResponse>>({});
  const autoBriefKey = useRef("");

  const campaigns = useQuery({
    queryKey: ["campaigns"],
    queryFn: () => apiFetch<{ rows: CampaignRow[] }>("/api/campaigns"),
  });
  const build = useQuery({ queryKey: ["build_info"], queryFn: () => apiFetch<BuildInfo>("/api/system/build_info") });

  const selectedCampaign = useMemo(
    () => (campaigns.data?.rows || []).find((row) => row.campaign_id === campaignId) || null,
    [campaignId, campaigns.data],
  );

  const latestAssistantTurn = [...turns].reverse().find((turn): turn is Extract<Turn, { role: "assistant" }> => turn.role === "assistant");
  const quickReplies = latestAssistantTurn?.response.quick_replies?.length ? latestAssistantTurn.response.quick_replies : FALLBACK_QUICK_REPLIES;
  const heroSummary = latestAssistantTurn?.response.summary?.length ? latestAssistantTurn.response.summary.slice(0, 4) : DEFAULT_HERO_SUMMARY;
  const heroEvidence = latestAssistantTurn?.response.evidence?.slice(0, 3) || [];
  const spotlightRecommendation = latestAssistantTurn?.response.recommendations?.[0] || null;

  async function fetchTurn(message: string) {
    const response = await apiFetch<ChatResponse>("/api/control-layer/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message,
        campaign_id: campaignId || undefined,
      }),
    });
    return response;
  }

  async function sendMessage(message: string) {
    const trimmed = message.trim();
    if (!trimmed || busy) {
      return;
    }
    const userTurn: Turn = { id: nextId("user"), role: "user", message: trimmed };
    setTurns((current) => [...current, userTurn]);
    setDraft("");
    setBusy(true);
    try {
      const response = await fetchTurn(trimmed);
      setTurns((current) => [...current, { id: nextId("assistant"), role: "assistant", response }]);
    } catch (error) {
      notifications.show({ color: "red", message: `Unable to reach the control layer: ${String(error)}` });
    } finally {
      setBusy(false);
    }
  }

  async function runAction(action: ActionProposal) {
    if (actionBusyId) {
      return;
    }
    setActionBusyId(action.id);
    try {
      const result = await apiFetch<ActionResponse>("/api/control-layer/actions", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          action_type: action.action_type,
          payload: action.payload,
        }),
      });
      setActionResults((current) => ({ ...current, [action.id]: result }));
      notifications.show({
        color: result.result_type === "experiment_created" ? "teal" : "blue",
        message: result.message,
      });
    } catch (error) {
      notifications.show({ color: "red", message: `Action failed: ${String(error)}` });
    } finally {
      setActionBusyId("");
    }
  }

  useEffect(() => {
    if (!campaigns.isSuccess) {
      return;
    }
    const scopeKey = campaignId || "__all__";
    if (autoBriefKey.current === scopeKey) {
      return;
    }
    autoBriefKey.current = scopeKey;
    setTurns([]);
    setActionResults({});
    setBusy(true);
    void (async () => {
      try {
        const response = await fetchTurn(DEFAULT_PROMPT);
        setTurns([
          { id: nextId("user"), role: "user", message: DEFAULT_PROMPT },
          { id: nextId("assistant"), role: "assistant", response },
        ]);
      } catch (error) {
        notifications.show({ color: "red", message: `Unable to generate the initial brief: ${String(error)}` });
      } finally {
        setBusy(false);
      }
    })();
  }, [campaignId, campaigns.isSuccess, campaigns.data]);

  if (campaigns.isLoading) {
    return (
      <Group justify="center" py="xl">
        <Loader />
      </Group>
    );
  }

  return (
    <Stack gap="lg" className="te-control-page">
      <ModuleHeader
        title="Operations Copilot"
        subtitle="A control-layer interface for reading the operation, diagnosing why a lane is winning or leaking, and turning evidence into governed action."
        badge="Agentic"
        action={
          <Group>
            <Select
              value={campaignId}
              onChange={(value) => setCampaignId(value || "")}
              placeholder="All campaigns"
              data={[{ value: "", label: "All campaigns" }, ...(campaigns.data?.rows || []).map((row) => ({ value: row.campaign_id, label: row.name || row.campaign_id }))]}
              w={250}
            />
            <Badge variant="light">Build {build.data?.static_token || "-"}</Badge>
          </Group>
        }
      />

      <Card className="te-control-hero" withBorder radius="xl" p="xl">
        <div className="te-control-hero-grid">
          <div className="te-control-hero-copy">
            <Badge className="te-control-hero-badge" variant="filled">
              Operational control layer
            </Badge>
            <Title className="te-control-hero-title">Turn collections metrics into decisions the team can actually run.</Title>
            <Text className="te-control-hero-subtitle">
              Ask what is working by campaign, bucket, agent, or account. The copilot explains the pattern, shows the evidence, estimates impact, and gives you the next action in the same surface.
            </Text>
            <Group gap="xs" className="te-control-hero-chips">
              <Badge variant="outline" className="te-control-hero-chip">
                Campaign to customer
              </Badge>
              <Badge variant="outline" className="te-control-hero-chip">
                Confidence-aware
              </Badge>
              <Badge variant="outline" className="te-control-hero-chip">
                Experiment-ready
              </Badge>
              <Badge variant="outline" className="te-control-hero-chip">
                Approval-governed
              </Badge>
            </Group>
          </div>

          <Paper className="te-control-scope-panel" radius="xl" p="lg">
            <Stack gap="md">
              <Group justify="space-between" align="flex-start">
                <div>
                  <Text className="te-control-panel-kicker">Current scope</Text>
                  <Title order={4} className="te-control-panel-title">
                    {selectedCampaign ? selectedCampaign.name : "All campaigns"}
                  </Title>
                </div>
                <Badge variant="light" color={busy ? "blue" : "teal"}>
                  {busy ? "Refreshing" : "Live"}
                </Badge>
              </Group>
              <Text className="te-control-panel-copy">
                {selectedCampaign
                  ? `${selectedCampaign.campaign_id} is active in the control layer. Recommendations and action payloads will be scoped to this campaign.`
                  : "The copilot is reading the full operating surface. Select one campaign to create a buyer-specific demo lane."}
              </Text>
              <div className="te-control-panel-meta">
                <div>
                  <Text className="te-control-panel-meta-label">Build token</Text>
                  <Text className="te-control-panel-meta-value">{build.data?.static_token || "-"}</Text>
                </div>
                <div>
                  <Text className="te-control-panel-meta-label">Quick mode</Text>
                  <Text className="te-control-panel-meta-value">Diagnose, simulate, execute</Text>
                </div>
              </div>
            </Stack>
          </Paper>
        </div>

        <SimpleGrid cols={{ base: 1, md: 2, xl: 4 }} className="te-control-hero-summary-grid">
          {heroSummary.map((item) => (
            <SummaryTile key={item.label} item={item} inverse />
          ))}
        </SimpleGrid>
      </Card>

      <Grid align="start" gutter="lg">
        <Grid.Col span={{ base: 12, xl: 8 }}>
          <Card className="te-control-console" withBorder radius="xl" p="xl">
            <Stack gap="lg">
              <Group justify="space-between" align="flex-start">
                <div>
                  <Text className="te-control-section-kicker">Copilot console</Text>
                  <Title order={3}>Read, decide, and trigger the next move.</Title>
                  <Text size="sm" c="dimmed" mt={6}>
                    {selectedCampaign
                      ? `Operating on ${selectedCampaign.name} (${selectedCampaign.campaign_id})`
                      : "Operating across all campaigns"}
                  </Text>
                </div>
                <Group gap="xs">
                  <Badge variant="light" color="blue">
                    Grounded analytics
                  </Badge>
                  <Badge variant="outline" color={busy ? "blue" : "teal"}>
                    {busy ? "Thinking" : "Ready"}
                  </Badge>
                </Group>
              </Group>

              {!turns.length && !busy ? (
                <EmptyStateCard
                  title="No operating brief yet"
                  description="Ask what is working by bucket or agent, or use a quick prompt to generate the first control-layer readout."
                />
              ) : null}

              <Stack gap="md" className="te-control-thread">
                {turns.map((turn) =>
                  turn.role === "user" ? (
                    <Group key={turn.id} justify="flex-end">
                      <Paper className="te-control-turn te-control-turn--user" radius="xl" p="md">
                        <Text className="te-control-turn-label te-control-turn-label--user">Operator prompt</Text>
                        <Text className="te-control-user-copy">{turn.message}</Text>
                      </Paper>
                    </Group>
                  ) : (
                    <AssistantTurn
                      key={turn.id}
                      turn={turn.response}
                      actionBusyId={actionBusyId}
                      actionResults={actionResults}
                      onRun={(action) => void runAction(action)}
                    />
                  ),
                )}
              </Stack>

              <Paper className="te-control-composer" radius="xl" p="lg">
                <Stack gap="md">
                  <Group justify="space-between" align="center">
                    <div>
                      <Text className="te-control-section-kicker">Prompt composer</Text>
                      <Text size="sm" c="dimmed">
                        Ask for diagnosis, recommendations, or a directional simulation before you trigger a governed action.
                      </Text>
                    </div>
                    <ThemeIcon className="te-control-composer-icon" size="xl" radius="xl">
                      <SendHorizontal size={18} />
                    </ThemeIcon>
                  </Group>

                  <div className="te-control-prompt-grid">
                    {quickReplies.map((prompt) => (
                      <Button key={prompt} variant="light" className="te-control-prompt-button" onClick={() => void sendMessage(prompt)}>
                        {prompt}
                      </Button>
                    ))}
                  </div>

                  <Textarea
                    label="Ask the control layer"
                    className="te-control-textarea"
                    placeholder="Example: Which bucket is underperforming, why, and what should I change this week?"
                    minRows={3}
                    maxRows={6}
                    autosize
                    value={draft}
                    onChange={(event) => setDraft(event.currentTarget.value)}
                  />
                  <Group justify="space-between" align="center">
                    <Text size="xs" c="dimmed">
                      Responses are grounded on live metrics and returned with evidence, confidence, and action options.
                    </Text>
                    <Button
                      className="te-control-send-button"
                      onClick={() => void sendMessage(draft)}
                      disabled={!draft.trim()}
                      loading={busy}
                      rightSection={<SendHorizontal size={14} />}
                    >
                      Send to copilot
                    </Button>
                  </Group>
                </Stack>
              </Paper>
            </Stack>
          </Card>
        </Grid.Col>

        <Grid.Col span={{ base: 12, xl: 4 }}>
          <Stack gap="lg">
            <Card className="te-control-rail-card te-control-rail-card--spotlight" withBorder radius="xl" p="lg">
              <Stack gap="md">
                <Group justify="space-between" align="flex-start">
                  <div>
                    <Text className="te-control-section-kicker">Decision spotlight</Text>
                    <Title order={4}>{spotlightRecommendation ? spotlightRecommendation.title : "Ask for the next best move"}</Title>
                  </div>
                  <ThemeIcon className="te-control-rail-icon" size="xl" radius="xl">
                    <Sparkles size={18} />
                  </ThemeIcon>
                </Group>
                <Text size="sm" c="dimmed">
                  {spotlightRecommendation
                    ? spotlightRecommendation.rationale
                    : "The strongest recommendation from the latest copilot readout will surface here with impact and execution controls."}
                </Text>
                {spotlightRecommendation ? <ImpactBand impact={spotlightRecommendation.expected_impact} /> : null}
                {spotlightRecommendation?.actions?.length ? (
                  <Stack gap="sm">
                    {spotlightRecommendation.actions.slice(0, 2).map((action) => (
                      <ActionTile
                        key={action.id}
                        action={action}
                        result={actionResults[action.id]}
                        busy={actionBusyId === action.id}
                        onRun={(proposal) => void runAction(proposal)}
                      />
                    ))}
                  </Stack>
                ) : null}
              </Stack>
            </Card>

            <Card className="te-control-rail-card" withBorder radius="xl" p="lg">
              <Stack gap="md">
                <Group justify="space-between" align="flex-start">
                  <div>
                    <Text className="te-control-section-kicker">Watchlist</Text>
                    <Title order={4}>What the control layer is watching</Title>
                  </div>
                  <ThemeIcon className="te-control-rail-icon te-control-rail-icon--alt" size="xl" radius="xl">
                    <Radar size={18} />
                  </ThemeIcon>
                </Group>
                {heroEvidence.length ? (
                  <Stack gap="sm">
                    {heroEvidence.map((item) => (
                      <Paper key={`${item.entity_type}-${item.entity_id || item.title}`} className="te-control-watch-item" radius="xl" p="md">
                        <Group justify="space-between" align="flex-start">
                          <div>
                            <Text fw={700} size="sm">
                              {item.title}
                            </Text>
                            <Text size="xs" c="dimmed">
                              {item.summary}
                            </Text>
                          </div>
                          <Badge variant="light" color={confidenceColor(item.confidence)}>
                            {item.confidence}
                          </Badge>
                        </Group>
                      </Paper>
                    ))}
                  </Stack>
                ) : (
                  <Text size="sm" c="dimmed">
                    Once a copilot readout is generated, the strongest evidence blocks surface here for a fast executive scan.
                  </Text>
                )}
              </Stack>
            </Card>

            <Card className="te-control-rail-card" withBorder radius="xl" p="lg">
              <Stack gap="md">
                <Group justify="space-between" align="flex-start">
                  <div>
                    <Text className="te-control-section-kicker">Operating brief</Text>
                    <Title order={4}>What this surface is built to do</Title>
                  </div>
                  <ThemeIcon className="te-control-rail-icon" size="xl" radius="xl">
                    <ShieldCheck size={18} />
                  </ThemeIcon>
                </Group>
                <div className="te-control-capability-list">
                  <Paper className="te-control-capability-item" radius="xl" p="md">
                    <Text fw={700} size="sm">
                      Explain performance
                    </Text>
                    <Text size="xs" c="dimmed">
                      Compare campaigns, buckets, agents, and customers from the same operating surface.
                    </Text>
                  </Paper>
                  <Paper className="te-control-capability-item" radius="xl" p="md">
                    <Text fw={700} size="sm">
                      Diagnose why
                    </Text>
                    <Text size="xs" c="dimmed">
                      Tie underperformance to discipline gaps, missed PTP pressure, alert load, and containment leakage.
                    </Text>
                  </Paper>
                  <Paper className="te-control-capability-item" radius="xl" p="md">
                    <Text fw={700} size="sm">
                      Recommend and execute
                    </Text>
                    <Text size="xs" c="dimmed">
                      Create experiments directly or submit strategy and routing changes through approval-aware actions.
                    </Text>
                  </Paper>
                </div>
              </Stack>
            </Card>
          </Stack>
        </Grid.Col>
      </Grid>
    </Stack>
  );
}
