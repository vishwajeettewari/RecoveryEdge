import {
  Badge,
  Button,
  Card,
  FileInput,
  Group,
  JsonInput,
  Loader,
  NumberInput,
  Select,
  SimpleGrid,
  Stack,
  Stepper,
  Table,
  Text,
  TextInput,
  Title,
} from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { useMemo, useState } from "react";

import { apiFetch } from "../../api/client";
import { FlowGuide } from "../../components/FlowGuide";
import { ModuleHeader } from "../../components/ModuleHeader";

interface ColumnInfo {
  source_col: string;
  inferred_type?: string;
  sample_values?: string[];
}

interface UploadResponse {
  upload_id: string;
  portfolio_id: string;
  columns: ColumnInfo[];
  sample_preview: Record<string, unknown>[];
  row_count: number;
}

const MAPPABLE_FIELDS = ["", "customer_id", "phone", "amount_due", "dpd", "due_date", "language", "customer_name"];

function inferMapping(columns: ColumnInfo[]): Record<string, string> {
  const out: Record<string, string> = {};
  columns.forEach((c) => {
    const n = (c.source_col || "").toLowerCase();
    if (n.includes("customer") && n.includes("id")) out[c.source_col] = "customer_id";
    else if (n === "phone" || n.includes("mobile")) out[c.source_col] = "phone";
    else if (n.includes("amount") || n.includes("due")) out[c.source_col] = "amount_due";
    else if (n === "dpd" || n.includes("days_past_due")) out[c.source_col] = "dpd";
    else if (n.includes("due_date") || n === "duedate") out[c.source_col] = "due_date";
    else if (n.includes("language")) out[c.source_col] = "language";
    else if (n.includes("name")) out[c.source_col] = "customer_name";
    else out[c.source_col] = "";
  });
  return out;
}

export function PortfolioPage() {
  const [active, setActive] = useState(0);
  const [busy, setBusy] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [exclusionFile, setExclusionFile] = useState<File | null>(null);
  const [upload, setUpload] = useState<UploadResponse | null>(null);
  const [mapping, setMapping] = useState<Record<string, string>>({});
  const [validation, setValidation] = useState<Record<string, unknown> | null>(null);
  const [previewRows, setPreviewRows] = useState<Record<string, unknown>[]>([]);
  const [campaignName, setCampaignName] = useState(`Campaign ${new Date().toISOString().slice(0, 10)}`);
  const [maxAttempts, setMaxAttempts] = useState(3);
  const [retryDelayMinutes, setRetryDelayMinutes] = useState(30);
  const [throttle, setThrottle] = useState(250);
  const [excludePredicate, setExcludePredicate] = useState("");
  const [exclusionUploadId, setExclusionUploadId] = useState<string | null>(null);

  const mappedRequired = useMemo(() => {
    const selected = new Set(Object.values(mapping).filter(Boolean));
    return ["customer_id", "phone", "amount_due", "dpd"].every((x) => selected.has(x));
  }, [mapping]);

  const onUpload = async () => {
    if (!file) return;
    setBusy(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const data = await apiFetch<UploadResponse>("/api/portfolio/upload", { method: "POST", body: fd });
      setUpload(data);
      setMapping(inferMapping(data.columns || []));
      setValidation(null);
      setPreviewRows(data.sample_preview || []);
      setActive(1);
      notifications.show({ color: "green", message: `Uploaded ${data.row_count} rows` });
    } catch (err) {
      notifications.show({ color: "red", message: String(err) });
    } finally {
      setBusy(false);
    }
  };

  const onMap = async () => {
    if (!upload) return;
    setBusy(true);
    try {
      const out = await apiFetch<{ portfolio_id: string }>(`/api/portfolio/${encodeURIComponent(upload.upload_id)}/map`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mappings: mapping, portfolio_name: `Portfolio ${new Date().toISOString().slice(0, 10)}` }),
      });
      setUpload({ ...upload, portfolio_id: out.portfolio_id });
      setActive(2);
      notifications.show({ color: "green", message: "Columns mapped" });
    } catch (err) {
      notifications.show({ color: "red", message: String(err) });
    } finally {
      setBusy(false);
    }
  };

  const onValidate = async () => {
    if (!upload?.portfolio_id) return;
    setBusy(true);
    try {
      const out = await apiFetch<Record<string, unknown>>(`/api/portfolio/${encodeURIComponent(upload.portfolio_id)}/validate`, { method: "POST" });
      const preview = await apiFetch<{ rows: Record<string, unknown>[] }>(`/api/portfolio/${encodeURIComponent(upload.portfolio_id)}/preview?limit=20`);
      setValidation(out);
      setPreviewRows(preview.rows || []);
      setActive(3);
      notifications.show({ color: "green", message: "Validation completed" });
    } catch (err) {
      notifications.show({ color: "red", message: String(err) });
    } finally {
      setBusy(false);
    }
  };

  const onUploadExclusions = async () => {
    if (!upload?.portfolio_id || !exclusionFile) return;
    setBusy(true);
    try {
      const fd = new FormData();
      fd.append("file", exclusionFile);
      const out = await apiFetch<{ exclusion_id: string; row_count: number }>(
        `/api/portfolio/${encodeURIComponent(upload.portfolio_id)}/exclusions/upload`,
        { method: "POST", body: fd }
      );
      setExclusionUploadId(out.exclusion_id);
      notifications.show({ color: "green", message: `Exclusions applied: ${out.row_count}` });
    } catch (err) {
      notifications.show({ color: "red", message: String(err) });
    } finally {
      setBusy(false);
    }
  };

  const onLaunch = async () => {
    if (!upload?.portfolio_id) return;
    setBusy(true);
    try {
      const out = await apiFetch<{ campaign_id: string; seeded_accounts: number; tasks_created: number }>(
        `/api/portfolio/${encodeURIComponent(upload.portfolio_id)}/launch`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            campaign_name: campaignName,
            retry_policy: { max_attempts: maxAttempts, retry_delay_minutes: retryDelayMinutes },
            contact_window: { start: "09:00", end: "20:00" },
            throttle,
            dpd_bucket_strategies: {},
            exclusion_upload_id: exclusionUploadId,
            exclude_predicate: excludePredicate || null,
          }),
        }
      );
      notifications.show({
        color: "green",
        message: `Campaign ${out.campaign_id} launched: seeded ${out.seeded_accounts}, tasks ${out.tasks_created}`,
      });
      setActive(4);
    } catch (err) {
      notifications.show({ color: "red", message: String(err) });
    } finally {
      setBusy(false);
    }
  };

  return (
    <Stack gap="md">
      <ModuleHeader
        title="Portfolios & Campaigns"
        subtitle="Bring portfolio data in, clean it, and launch campaigns with confidence"
        action={busy ? <Loader size="sm" /> : null}
      />

      <FlowGuide
        title="Portfolio Launch Flow"
        steps={[
          { title: "Upload File", detail: "Drop CSV/XLSX from LMS export" },
          { title: "Map Columns", detail: "Map required fields once" },
          { title: "Validate Data", detail: "Fix errors and verify quality score" },
          { title: "Launch Campaign", detail: "Set retries/throttle and start" },
        ]}
      />

      <Card className="te-section-card">
        <Stepper active={active} onStepClick={setActive} allowNextStepsSelect>
          <Stepper.Step label="Upload" description="CSV/XLSX">
            <Stack mt="md">
              <Group align="flex-end">
                <FileInput label="Portfolio file" placeholder="Choose CSV/XLSX" value={file} onChange={setFile} accept=".csv,.xlsx" />
                <Button onClick={onUpload} disabled={!file || busy}>Upload</Button>
              </Group>
              {upload ? (
                <Text size="sm" c="dimmed">
                  upload_id={upload.upload_id} | portfolio_id={upload.portfolio_id} | rows={upload.row_count}
                </Text>
              ) : null}
              <JsonInput label="Preview sample" value={JSON.stringify(upload?.sample_preview || [], null, 2)} autosize minRows={6} readOnly />
            </Stack>
          </Stepper.Step>

          <Stepper.Step label="Map" description="Required fields">
            <Stack mt="md">
              <Table striped>
                <Table.Thead>
                  <Table.Tr>
                    <Table.Th>Source Column</Table.Th>
                    <Table.Th>Map to</Table.Th>
                    <Table.Th>Type</Table.Th>
                  </Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {(upload?.columns || []).map((col) => (
                    <Table.Tr key={col.source_col}>
                      <Table.Td>{col.source_col}</Table.Td>
                      <Table.Td>
                        <Select
                          data={MAPPABLE_FIELDS.map((v) => ({ value: v, label: v || "(ignore)" }))}
                          value={mapping[col.source_col] || ""}
                          onChange={(v) => setMapping((prev) => ({ ...prev, [col.source_col]: v || "" }))}
                        />
                      </Table.Td>
                      <Table.Td>{col.inferred_type || "string"}</Table.Td>
                    </Table.Tr>
                  ))}
                </Table.Tbody>
              </Table>
              <Group justify="space-between">
                <Badge color={mappedRequired ? "green" : "orange"} variant="light">
                  {mappedRequired ? "Required fields mapped" : "Map customer_id, phone, amount_due, dpd"}
                </Badge>
                <Button onClick={onMap} disabled={!upload || !mappedRequired || busy}>Save Mapping</Button>
              </Group>
            </Stack>
          </Stepper.Step>

          <Stepper.Step label="Validate" description="Data quality">
            <Stack mt="md">
              <Group>
                <Button onClick={onValidate} disabled={!upload?.portfolio_id || busy}>Validate Portfolio</Button>
                {upload?.portfolio_id ? (
                  <Button component="a" href={`/api/portfolio/${encodeURIComponent(upload.portfolio_id)}/errors.csv`} target="_blank" variant="light">
                    Download errors.csv
                  </Button>
                ) : null}
              </Group>
              {validation ? (
                <SimpleGrid cols={{ base: 1, md: 3 }}>
                  <Card>
                    <Text size="sm" c="dimmed">Data Quality Score</Text>
                    <Title order={3}>{String(validation.data_quality_score ?? "-")}</Title>
                  </Card>
                  <Card>
                    <Text size="sm">Valid rows: {String(validation.valid_rows ?? "-")}</Text>
                    <Text size="sm">Invalid rows: {String(validation.invalid_rows ?? "-")}</Text>
                    <Text size="sm">Duplicates dropped: {String(validation.duplicates_dropped ?? "-")}</Text>
                  </Card>
                  <Card>
                    <Text size="sm" fw={600}>Top Issues</Text>
                    <JsonInput value={JSON.stringify(validation.top_issues || [], null, 2)} autosize minRows={4} readOnly />
                  </Card>
                </SimpleGrid>
              ) : null}
            </Stack>
          </Stepper.Step>

          <Stepper.Step label="Preview" description="Valid rows">
            <Stack mt="md">
              <Text size="sm" c="dimmed">First 20 valid rows ready for campaign seeding.</Text>
              <JsonInput value={JSON.stringify(previewRows || [], null, 2)} autosize minRows={8} readOnly />
              <Group justify="flex-end">
                <Button onClick={() => setActive(4)} disabled={!previewRows.length}>Proceed to Launch</Button>
              </Group>
            </Stack>
          </Stepper.Step>

          <Stepper.Step label="Launch" description="Campaign config">
            <Stack mt="md">
              <SimpleGrid cols={{ base: 1, md: 3 }}>
                <TextInput label="Campaign name" value={campaignName} onChange={(e) => setCampaignName(e.currentTarget.value)} />
                <NumberInput label="Max attempts" value={maxAttempts} onChange={(v) => setMaxAttempts(Number(v) || 3)} min={1} max={10} />
                <NumberInput label="Retry delay (minutes)" value={retryDelayMinutes} onChange={(v) => setRetryDelayMinutes(Number(v) || 30)} min={1} max={720} />
                <NumberInput label="Throttle (batch size)" value={throttle} onChange={(v) => setThrottle(Number(v) || 250)} min={1} max={10000} />
                <TextInput label="Exclude predicate" placeholder="dpd<1,amount_due<50" value={excludePredicate} onChange={(e) => setExcludePredicate(e.currentTarget.value)} />
              </SimpleGrid>
              <Group align="flex-end">
                <FileInput label="Exclude rows CSV" value={exclusionFile} onChange={setExclusionFile} accept=".csv" />
                <Button variant="light" onClick={onUploadExclusions} disabled={!upload?.portfolio_id || !exclusionFile || busy}>
                  Upload Exclusions
                </Button>
                {exclusionUploadId ? <Badge variant="light">{exclusionUploadId}</Badge> : null}
              </Group>
              <Group justify="space-between">
                <Text size="sm" c="dimmed">Only valid, deduplicated rows are seeded into the campaign.</Text>
                <Button onClick={onLaunch} disabled={!upload?.portfolio_id || busy}>Launch Campaign</Button>
              </Group>
            </Stack>
          </Stepper.Step>

          <Stepper.Completed>
            <Card>
              <Title order={4}>Campaign launched successfully</Title>
              <Text c="dimmed">Proceed to Workbench or Calling Console to start execution.</Text>
            </Card>
          </Stepper.Completed>
        </Stepper>
      </Card>
    </Stack>
  );
}
