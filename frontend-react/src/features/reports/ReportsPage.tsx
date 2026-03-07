import { Button, Card, Group, ScrollArea, Select, Stack, Switch, Table, Text, TextInput, Title } from "@mantine/core";
import dayjs from "dayjs";
import { notifications } from "@mantine/notifications";
import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarDays, DownloadCloud } from "lucide-react";

import { apiFetch } from "../../api/client";
import { useAuth } from "../../auth/AuthProvider";
import { PERMS } from "../../auth/roles";
import { FlowGuide } from "../../components/FlowGuide";
import { ModuleHeader } from "../../components/ModuleHeader";
import { EmptyStateCard } from "../../components/EmptyStateCard";
import type { CampaignRow, ReportRow } from "../../types/api";

interface ReportsResponse {
  rows: ReportRow[];
  total: number;
  schedule: { enabled: number; daily_time: string };
}

function reportFileName(row: ReportRow, format: "json" | "csv"): string {
  return `recovery_report_${row.campaign_id}_${row.report_date}.${format}`;
}

export function ReportsPage() {
  const { hasPermission } = useAuth();
  const canSchedule = hasPermission(PERMS.REPORTS_SCHEDULE);
  const qc = useQueryClient();

  const [enabled, setEnabled] = useState(true);
  const [dailyTime, setDailyTime] = useState("09:00");
  const [campaignId, setCampaignId] = useState("");

  const reportsQuery = useQuery({
    queryKey: ["reports", campaignId],
    queryFn: () => apiFetch<ReportsResponse>(`/api/reports${campaignId ? `?campaign_id=${encodeURIComponent(campaignId)}` : ""}`),
  });

  const campaignsQuery = useQuery({
    queryKey: ["campaigns_for_reports"],
    queryFn: () => apiFetch<{ rows: CampaignRow[] }>("/api/campaigns"),
  });

  const refresh = async () => {
    await qc.invalidateQueries({ queryKey: ["reports"] });
  };

  const onSaveSchedule = async () => {
    await apiFetch("/api/reports/schedule", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled, daily_time: dailyTime }),
    });
    notifications.show({ color: "green", message: "Schedule updated" });
    await refresh();
  };

  const onGenerate = async () => {
    await apiFetch("/api/reports/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ campaign_id: campaignId || undefined }),
    });
    notifications.show({ color: "green", message: "Report generation started" });
    await refresh();
  };

  return (
    <Stack>
      <ModuleHeader
        title="Reports"
        subtitle="Daily operations reporting with one-click generation and download"
        action={<Button variant="light" onClick={refresh}>Refresh</Button>}
      />

      <FlowGuide
        title="Reports Flow"
        steps={[
          { title: "Choose Scope", detail: "All campaigns or a specific campaign" },
          { title: "Schedule", detail: "Set daily report time for auto run" },
          { title: "Generate", detail: "Trigger immediate report if required" },
          { title: "Download", detail: "Export JSON/CSV from history table" },
        ]}
      />

      <Card className="te-section-card te-data-card">
        <Title order={4} mb="sm">Schedule</Title>
        <Group align="end">
          <Switch checked={enabled} onChange={(e) => setEnabled(e.currentTarget.checked)} label="Daily schedule" disabled={!canSchedule} />
          <TextInput label="HH:MM" value={dailyTime} onChange={(e) => setDailyTime(e.currentTarget.value)} disabled={!canSchedule} leftSection={<CalendarDays size={14} />} />
          <Select
            label="Campaign"
            placeholder="All campaigns"
            value={campaignId}
            onChange={(v) => setCampaignId(v || "")}
            data={[{ value: "", label: "All campaigns" }, ...(campaignsQuery.data?.rows || []).map((r) => ({ value: r.campaign_id, label: `${r.name} (${r.campaign_id})` }))]}
          />
          {canSchedule ? <Button onClick={onSaveSchedule}>Save Schedule</Button> : null}
          {canSchedule ? <Button variant="light" onClick={onGenerate}>Generate Now</Button> : null}
        </Group>
        <Text size="sm" c="dimmed" mt="sm">
          Current schedule: {reportsQuery.data?.schedule?.enabled ? "enabled" : "disabled"} at {reportsQuery.data?.schedule?.daily_time || "09:00"}
        </Text>
      </Card>

      <Card className="te-section-card te-data-card">
        <Group justify="space-between" mb="sm">
          <Title order={4}>Download Center</Title>
          <Text size="sm" c="dimmed">JSON + CSV exports with stable schema</Text>
        </Group>
        {(reportsQuery.data?.rows || []).length ? (
          <ScrollArea className="te-table-wrap te-subtle-scroll" offsetScrollbars>
            <Table>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>Report</Table.Th>
                  <Table.Th>Campaign</Table.Th>
                  <Table.Th>Date</Table.Th>
                  <Table.Th>Created</Table.Th>
                  <Table.Th>Downloads</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {(reportsQuery.data?.rows || []).map((r) => (
                  <Table.Tr key={r.id}>
                    <Table.Td>{r.id}</Table.Td>
                    <Table.Td>{r.campaign_id}</Table.Td>
                    <Table.Td>{r.report_date}</Table.Td>
                    <Table.Td>{dayjs.unix(r.created_at).format("DD MMM YYYY HH:mm")}</Table.Td>
                    <Table.Td>
                      <Group gap={8}>
                        <a href={`/api/reports/${encodeURIComponent(r.id)}/download?format=json`} target="_blank" rel="noreferrer" download={reportFileName(r, "json")}>
                          <Group gap={4}><DownloadCloud size={14} /><span>JSON</span></Group>
                        </a>
                        <a href={`/api/reports/${encodeURIComponent(r.id)}/download?format=csv`} target="_blank" rel="noreferrer" download={reportFileName(r, "csv")}>
                          <Group gap={4}><DownloadCloud size={14} /><span>CSV</span></Group>
                        </a>
                      </Group>
                    </Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          </ScrollArea>
        ) : (
          <EmptyStateCard title="No reports yet" description="Generate the first report or enable schedule to populate this download center." />
        )}
      </Card>
    </Stack>
  );
}
