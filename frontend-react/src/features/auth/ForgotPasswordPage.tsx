import { Button, Card, Center, PasswordInput, Stack, Text, TextInput, Title } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { useState } from "react";
import { Link } from "react-router-dom";

import { apiFetch } from "../../api/client";

export function ForgotPasswordPage() {
  const [usernameOrEmail, setUsernameOrEmail] = useState("");
  const [token, setToken] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [requesting, setRequesting] = useState(false);
  const [resetting, setResetting] = useState(false);
  const [previewToken, setPreviewToken] = useState("");

  const requestReset = async () => {
    setRequesting(true);
    try {
      const out = await apiFetch<{ ok: boolean; message: string; reset_token_preview?: string }>("/api/auth/forgot-password", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username_or_email: usernameOrEmail }),
      });
      if (out.reset_token_preview) {
        setPreviewToken(out.reset_token_preview);
      }
      notifications.show({ color: "green", message: out.message || "If the account exists, reset instructions were sent." });
    } finally {
      setRequesting(false);
    }
  };

  const completeReset = async () => {
    setResetting(true);
    try {
      await apiFetch("/api/auth/reset-password", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token, new_password: newPassword }),
      });
      notifications.show({ color: "green", message: "Password updated. You can sign in now." });
      setToken("");
      setNewPassword("");
    } finally {
      setResetting(false);
    }
  };

  return (
    <Center h="100vh" style={{ background: "linear-gradient(135deg, #eef4ff 0%, #f5fbff 100%)" }}>
      <Card withBorder shadow="md" radius="md" maw={480} w="92vw">
        <Stack>
          <Title order={3}>Reset Password</Title>
          <Text size="sm" c="dimmed">
            Request a reset token and complete password reset. In production, account existence is never disclosed.
          </Text>
          <TextInput
            label="Username or email"
            placeholder="name@company.com"
            value={usernameOrEmail}
            onChange={(e) => setUsernameOrEmail(e.currentTarget.value)}
          />
          <Button loading={requesting} onClick={requestReset} disabled={!usernameOrEmail.trim()}>
            Request Reset
          </Button>
          {previewToken ? (
            <Text size="sm" c="teal">
              Demo reset token: {previewToken}
            </Text>
          ) : null}
          <TextInput
            label="Reset token"
            placeholder="Paste token from reset channel"
            value={token}
            onChange={(e) => setToken(e.currentTarget.value)}
          />
          <PasswordInput
            label="New password"
            placeholder="At least 12 chars, with upper/lower/number/special"
            value={newPassword}
            onChange={(e) => setNewPassword(e.currentTarget.value)}
          />
          <Button loading={resetting} onClick={completeReset} disabled={!token.trim() || !newPassword.trim()}>
            Complete Reset
          </Button>
          <Button component={Link} to="/login" variant="light">
            Back to login
          </Button>
        </Stack>
      </Card>
    </Center>
  );
}
