import { Badge, Button, Card, Group, JsonInput, Select, Stack, Switch, Text, Title } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";

import { apiFetch } from "../../api/client";
import { ModuleHeader } from "../../components/ModuleHeader";
import type { AuthMeResponse, BuildInfo } from "../../types/api";

interface HealthPayload {
  status: string;
  build: BuildInfo;
  ts: number;
}

interface TenantSettingsResponse {
  tenant: {
    tenant_id: string;
    name: string;
    settings: Record<string, unknown>;
  };
}

export function SettingsPage() {
  const me = useQuery({ queryKey: ["auth_me"], queryFn: () => apiFetch<AuthMeResponse>("/api/auth/me") });
  const build = useQuery({ queryKey: ["build_info"], queryFn: () => apiFetch<BuildInfo>("/api/system/build_info") });
  const [selectedTenant, setSelectedTenant] = useState<string>("");
  const [settingsJson, setSettingsJson] = useState<string>("");

  const tenantOptions = useMemo(() => {
    const ids = (me.data?.tenant_ids || []).filter(Boolean);
    return ids.map((id) => ({ value: id, label: id }));
  }, [me.data?.tenant_ids]);

  useEffect(() => {
    if (!selectedTenant) {
      const fallback = me.data?.default_tenant_id || me.data?.tenant_ids?.[0] || "default";
      setSelectedTenant(fallback);
    }
  }, [me.data?.default_tenant_id, me.data?.tenant_ids, selectedTenant]);

  const tenantSettings = useQuery({
    queryKey: ["tenant_settings", selectedTenant],
    enabled: !!selectedTenant,
    queryFn: () => apiFetch<TenantSettingsResponse>(`/api/settings/tenant?tenant_id=${encodeURIComponent(selectedTenant)}`),
  });

  useEffect(() => {
    const settings = tenantSettings.data?.tenant?.settings;
    if (settings) {
      setSettingsJson(JSON.stringify(settings, null, 2));
    }
  }, [tenantSettings.data?.tenant?.settings, selectedTenant]);

  const saveSettings = useMutation({
    mutationFn: async () => {
      let parsed: Record<string, unknown> = {};
      try {
        parsed = settingsJson.trim() ? (JSON.parse(settingsJson) as Record<string, unknown>) : {};
      } catch {
        throw new Error("Settings JSON is invalid");
      }
      return apiFetch<TenantSettingsResponse>(`/api/settings/tenant?tenant_id=${encodeURIComponent(selectedTenant)}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ settings: parsed }),
      });
    },
    onSuccess: (payload) => {
      setSettingsJson(JSON.stringify(payload.tenant.settings || {}, null, 2));
      notifications.show({ color: "green", message: "Tenant settings updated" });
    },
    onError: (err) => {
      notifications.show({ color: "red", message: err instanceof Error ? err.message : "Unable to update settings" });
    },
  });

  const health = useQuery({
    queryKey: ["api_health"],
    queryFn: async () => {
      const b = await apiFetch<BuildInfo>("/api/system/build_info");
      const payload: HealthPayload = { status: "ok", build: b, ts: Date.now() };
      return payload;
    },
  });

  return (
    <Stack>
      <ModuleHeader title="Settings" subtitle="Environment visibility, organization defaults, and API health" />

      <Card>
        <Title order={4} mb="sm">Environment</Title>
        <Group>
          <Switch checked={!!build.data?.demo_mode} readOnly label="DEMO_MODE" />
          <Switch checked={!!build.data?.pilot_mode} readOnly label="PILOT_MODE" />
          <Badge variant="outline">BUILD {build.data?.static_token || "-"}</Badge>
        </Group>
      </Card>

      <Card>
        <Group justify="space-between" mb="sm">
          <Title order={4}>Organization Settings</Title>
          <Select
            label="Tenant"
            data={tenantOptions}
            value={selectedTenant}
            onChange={(value) => setSelectedTenant(value || "")}
            maw={220}
          />
        </Group>
        <JsonInput
          value={settingsJson}
          onChange={setSettingsJson}
          autosize
          minRows={6}
        />
        <Group justify="flex-end" mt="sm">
          <Button variant="light" onClick={() => tenantSettings.refetch()} loading={tenantSettings.isFetching}>
            Reload
          </Button>
          <Button onClick={() => saveSettings.mutate()} loading={saveSettings.isPending}>
            Save
          </Button>
        </Group>
        <Text size="xs" c="dimmed" mt="sm">
          Applies to tenant {selectedTenant || "default"} with server-side permission and tenant checks.
        </Text>
      </Card>

      <Card>
        <Group justify="space-between" mb="sm">
          <Title order={4}>API Health</Title>
          <Button variant="light" onClick={() => health.refetch()}>Refresh</Button>
        </Group>
        <JsonInput value={JSON.stringify(health.data || {}, null, 2)} autosize minRows={6} readOnly />
      </Card>
    </Stack>
  );
}
