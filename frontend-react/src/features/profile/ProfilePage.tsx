import { Button, Card, Group, Stack, Table, Text, TextInput, Title } from "@mantine/core";
import { zodResolver } from "@hookform/resolvers/zod";
import { notifications } from "@mantine/notifications";
import dayjs from "dayjs";
import { useForm } from "react-hook-form";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";

import { apiFetch } from "../../api/client";
import { useAuth } from "../../auth/AuthProvider";
import { ModuleHeader } from "../../components/ModuleHeader";
import type { UserSession } from "../../types/api";

const schema = z
  .object({
    current_password: z.string().min(1, "Current password required"),
    new_password: z
      .string()
      .min(12, "Password must be at least 12 characters")
      .regex(/[A-Z]/, "Must include uppercase letter")
      .regex(/[a-z]/, "Must include lowercase letter")
      .regex(/[0-9]/, "Must include a number")
      .regex(/[^A-Za-z0-9]/, "Must include a special character"),
    confirm_password: z.string().min(12, "Confirm password required"),
  })
  .refine((v) => v.new_password === v.confirm_password, {
    message: "Passwords do not match",
    path: ["confirm_password"],
  });

type FormValues = z.infer<typeof schema>;

export function ProfilePage() {
  const { user } = useAuth();
  const qc = useQueryClient();

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
    reset,
  } = useForm<FormValues>({ resolver: zodResolver(schema) });

  const sessionsQuery = useQuery({
    queryKey: ["auth_sessions"],
    queryFn: () => apiFetch<{ rows: UserSession[] }>("/api/auth/sessions"),
  });

  const onSubmit = async (values: FormValues) => {
    await apiFetch("/api/auth/change_password", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ current_password: values.current_password, new_password: values.new_password }),
    });
    notifications.show({ color: "green", message: "Password changed" });
    reset();
  };

  const revokeSession = async (sessionId: string) => {
    await apiFetch(`/api/auth/sessions/${encodeURIComponent(sessionId)}/revoke`, { method: "POST" });
    notifications.show({ color: "green", message: "Session revoked" });
    await qc.invalidateQueries({ queryKey: ["auth_sessions"] });
  };

  return (
    <Stack>
      <ModuleHeader title="Profile" subtitle="User identity, credentials, and account activity" />

      <Card>
        <Title order={4} mb="sm">Account</Title>
        <Stack>
          <TextInput label="Username" value={user?.username || ""} readOnly />
          <TextInput label="Full name" value={user?.full_name || ""} readOnly />
          <TextInput label="Email" value={user?.email || ""} readOnly />
          <TextInput label="Role" value={user?.role || ""} readOnly />
        </Stack>
      </Card>

      <Card>
        <Title order={4} mb="sm">Change Password</Title>
        <form onSubmit={handleSubmit(onSubmit)}>
          <Stack>
            <TextInput label="Current password" type="password" {...register("current_password")} error={errors.current_password?.message} />
            <TextInput label="New password" type="password" {...register("new_password")} error={errors.new_password?.message} />
            <TextInput label="Confirm password" type="password" {...register("confirm_password")} error={errors.confirm_password?.message} />
            <Group justify="flex-end">
              <Button type="submit" loading={isSubmitting}>Update Password</Button>
            </Group>
          </Stack>
        </form>
      </Card>

      <Card>
        <Group justify="space-between" mb="sm">
          <Title order={4}>Sessions</Title>
          <Button variant="light" size="xs" onClick={() => sessionsQuery.refetch()} loading={sessionsQuery.isFetching}>
            Refresh
          </Button>
        </Group>
        <Table>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>Session</Table.Th>
              <Table.Th>Tenant</Table.Th>
              <Table.Th>Device</Table.Th>
              <Table.Th>IP</Table.Th>
              <Table.Th>Created</Table.Th>
              <Table.Th>Last Active</Table.Th>
              <Table.Th>Status</Table.Th>
              <Table.Th>Action</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {(sessionsQuery.data?.rows || []).map((s) => (
              <Table.Tr key={s.id}>
                <Table.Td>{s.id}</Table.Td>
                <Table.Td>{s.tenant_id || "-"}</Table.Td>
                <Table.Td>{s.user_agent || "Unknown"}</Table.Td>
                <Table.Td>{s.ip_addr || "-"}</Table.Td>
                <Table.Td>{s.created_at ? dayjs.unix(s.created_at).format("DD MMM YYYY HH:mm") : "-"}</Table.Td>
                <Table.Td>{s.last_seen_at ? dayjs.unix(s.last_seen_at).format("DD MMM YYYY HH:mm") : "-"}</Table.Td>
                <Table.Td>
                  {s.revoked_at ? <Text c="red">Revoked</Text> : <Text c="green">Active</Text>}
                </Table.Td>
                <Table.Td>
                  {!s.revoked_at ? (
                    <Button size="xs" variant="light" color="red" onClick={() => revokeSession(s.id)}>
                      Revoke
                    </Button>
                  ) : (
                    "-"
                  )}
                </Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      </Card>
    </Stack>
  );
}
