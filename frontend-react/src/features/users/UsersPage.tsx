import {
  Badge,
  Button,
  Card,
  Group,
  Modal,
  ScrollArea,
  Select,
  Stack,
  Switch,
  Table,
  Text,
  PasswordInput,
  TextInput,
  Title,
} from "@mantine/core";
import dayjs from "dayjs";
import { notifications } from "@mantine/notifications";
import { useState } from "react";
import { useDisclosure } from "@mantine/hooks";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { apiFetch } from "../../api/client";
import { EmptyStateCard } from "../../components/EmptyStateCard";
import { ModuleHeader } from "../../components/ModuleHeader";
import type { User } from "../../types/api";

const ROLES = ["ADMIN", "CEO", "CFO", "COLLECTIONS_MANAGER", "CALLING_AGENT", "COMPLIANCE_OFFICER", "VIEWER"];

export function UsersPage() {
  const qc = useQueryClient();
  const [opened, { open, close }] = useDisclosure(false);
  const [resetOpened, { open: openReset, close: closeReset }] = useDisclosure(false);

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<string>("CALLING_AGENT");
  const [lastAuditText, setLastAuditText] = useState("No recent admin action.");
  const [resetTarget, setResetTarget] = useState<User | null>(null);
  const [resetPasswordValue, setResetPasswordValue] = useState("");

  const usersQuery = useQuery({ queryKey: ["users"], queryFn: () => apiFetch<{ rows: User[] }>("/api/users") });

  const refresh = async () => {
    await qc.invalidateQueries({ queryKey: ["users"] });
  };

  const createUser = async () => {
    await apiFetch("/api/users", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password, full_name: fullName, email, role, is_active: true }),
    });
    notifications.show({ color: "green", message: "User created" });
    setLastAuditText(`[${dayjs().format("HH:mm:ss")}] CREATE_USER username=${username} role=${role}`);
    setUsername("");
    setPassword("");
    setFullName("");
    setEmail("");
    setRole("CALLING_AGENT");
    close();
    await refresh();
  };

  const patchUser = async (id: string, patch: Record<string, unknown>, label: string) => {
    await apiFetch(`/api/users/${encodeURIComponent(id)}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(patch),
    });
    setLastAuditText(`[${dayjs().format("HH:mm:ss")}] ${label} user_id=${id}`);
    await refresh();
  };

  const openResetModal = (u: User) => {
    setResetTarget(u);
    setResetPasswordValue("");
    openReset();
  };

  const resetPassword = async () => {
    if (!resetTarget) return;
    const out = await apiFetch<{ ok: boolean; must_change_password?: boolean; temporary_password?: string }>(
      `/api/users/${encodeURIComponent(resetTarget.id)}/reset_password`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(resetPasswordValue.trim() ? { new_password: resetPasswordValue } : {}),
      }
    );
    const msg = out.temporary_password ? `Temporary password: ${out.temporary_password}` : "Password reset completed";
    notifications.show({ color: "green", message: msg });
    setLastAuditText(`[${dayjs().format("HH:mm:ss")}] RESET_PASSWORD user_id=${resetTarget.id}`);
    closeReset();
    setResetTarget(null);
    setResetPasswordValue("");
  };

  return (
    <Stack>
      <ModuleHeader
        title="Users & Access"
        subtitle="Manage platform users, roles, activation, and credential reset"
        action={<Button onClick={open}>Create User</Button>}
      />

      <Card className="te-data-card">
        {(usersQuery.data?.rows || []).length ? (
          <ScrollArea className="te-table-wrap te-subtle-scroll" offsetScrollbars>
            <Table>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>Username</Table.Th>
                  <Table.Th>Name</Table.Th>
                  <Table.Th>Role</Table.Th>
                  <Table.Th>Active</Table.Th>
                  <Table.Th>Created</Table.Th>
                  <Table.Th>Last Login</Table.Th>
                  <Table.Th>Actions</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {(usersQuery.data?.rows || []).map((u) => (
                  <Table.Tr key={u.id}>
                    <Table.Td>{u.username}</Table.Td>
                    <Table.Td>{u.full_name || "-"}</Table.Td>
                    <Table.Td>
                      <Select
                        size="xs"
                        data={ROLES}
                        value={u.role}
                        onChange={(v) => patchUser(u.id, { role: v }, `CHANGE_ROLE -> ${v}`)}
                        allowDeselect={false}
                      />
                    </Table.Td>
                    <Table.Td>
                      <Switch checked={!!u.is_active} onChange={(e) => patchUser(u.id, { is_active: e.currentTarget.checked }, `TOGGLE_ACTIVE -> ${e.currentTarget.checked}`)} />
                    </Table.Td>
                    <Table.Td>{u.created_at ? dayjs.unix(u.created_at).format("DD MMM YYYY") : "-"}</Table.Td>
                    <Table.Td>{u.last_login_at ? dayjs.unix(u.last_login_at).format("DD MMM HH:mm") : "-"}</Table.Td>
                    <Table.Td>
                      <Button size="xs" variant="light" onClick={() => openResetModal(u)}>
                        Reset Password
                      </Button>
                    </Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          </ScrollArea>
        ) : (
          <EmptyStateCard title="No users found" description="Create platform users with roles to unlock dashboard and operations access." />
        )}
      </Card>

      <Card className="te-data-card">
        <Group justify="space-between">
          <Text fw={600}>Access Admin Activity</Text>
          <Badge variant="outline">Demo audit preview</Badge>
        </Group>
        <Text size="sm" c="dimmed" mt="xs">
          {lastAuditText}
        </Text>
      </Card>

      <Modal opened={opened} onClose={close} title="Create user" size="lg">
        <Stack>
          <TextInput label="Username" value={username} onChange={(e) => setUsername(e.currentTarget.value)} />
          <PasswordInput label="Password" value={password} onChange={(e) => setPassword(e.currentTarget.value)} />
          <TextInput label="Full name" value={fullName} onChange={(e) => setFullName(e.currentTarget.value)} />
          <TextInput label="Email" value={email} onChange={(e) => setEmail(e.currentTarget.value)} />
          <Select label="Role" value={role} onChange={(v) => setRole(v || "CALLING_AGENT")} data={ROLES} allowDeselect={false} />
          <Group justify="flex-end">
            <Button variant="light" onClick={close}>Cancel</Button>
            <Button onClick={createUser}>Create</Button>
          </Group>
        </Stack>
      </Modal>

      <Modal opened={resetOpened} onClose={closeReset} title="Reset password" size="md">
        <Stack>
          <Text size="sm" c="dimmed">
            {resetTarget ? `Reset credentials for ${resetTarget.username}.` : "Select a user first."}
          </Text>
          <PasswordInput
            label="Temporary password (optional)"
            placeholder="Leave blank to auto-generate"
            value={resetPasswordValue}
            onChange={(e) => setResetPasswordValue(e.currentTarget.value)}
          />
          <Text size="xs" c="dimmed">
            Server enforces enterprise password policy and marks user to change password on next login.
          </Text>
          <Group justify="flex-end">
            <Button variant="light" onClick={closeReset}>Cancel</Button>
            <Button onClick={resetPassword} disabled={!resetTarget}>Confirm Reset</Button>
          </Group>
        </Stack>
      </Modal>
    </Stack>
  );
}
