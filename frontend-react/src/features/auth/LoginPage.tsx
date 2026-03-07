import {
  Anchor,
  BackgroundImage,
  Badge,
  Button,
  Card,
  Center,
  Divider,
  Group,
  Paper,
  PasswordInput,
  Stack,
  Text,
  TextInput,
  Title,
} from "@mantine/core";
import { zodResolver } from "@hookform/resolvers/zod";
import { useQuery } from "@tanstack/react-query";
import { ShieldCheck } from "lucide-react";
import { useForm } from "react-hook-form";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { z } from "zod";

import turingEdgeLogo from "../../assets/turingedge-logo.png";
import { apiFetch, ApiError } from "../../api/client";
import { useAuth } from "../../auth/AuthProvider";
import type { BuildInfo } from "../../types/api";

const schema = z.object({
  username: z.string().min(1, "Username required"),
  password: z.string().min(1, "Password required"),
});

type FormValues = z.infer<typeof schema>;

export function LoginPage() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const { login } = useAuth();

  const build = useQuery({
    queryKey: ["public_build"],
    queryFn: () => apiFetch<BuildInfo>("/api/public/build_info"),
    retry: false,
  });

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
    setError,
  } = useForm<FormValues>({ resolver: zodResolver(schema) });

  const onSubmit = async (values: FormValues) => {
    try {
      await login(values.username, values.password);
      const next = params.get("next") || "/app";
      navigate(next, { replace: true });
    } catch (err) {
      const msg = err instanceof ApiError ? (typeof err.payload === "string" ? err.payload : JSON.stringify(err.payload)) : "Login failed";
      setError("root", { message: msg });
    }
  };

  return (
    <Center h="100vh" style={{ background: "linear-gradient(135deg, #eaf1ff 0%, #f2f8ff 45%, #eaf8f4 100%)" }}>
      <Card shadow="lg" radius="lg" p={0} w={940} maw="94vw" withBorder>
        <Group align="stretch" gap={0} wrap="nowrap">
          <BackgroundImage
            src="https://images.unsplash.com/photo-1582407947304-fd86f028f716?auto=format&fit=crop&w=1200&q=80"
            style={{ flex: 1, minHeight: 560, display: "none" }}
            visibleFrom="md"
          >
            <Stack h="100%" justify="space-between" p="xl" style={{ background: "linear-gradient(180deg, rgba(4,24,52,0.55), rgba(8,41,76,0.82))" }}>
              <img src={turingEdgeLogo} alt="TuringEdge" style={{ width: 210, filter: "brightness(0) invert(1)" }} />
              <Stack gap="sm" c="white">
                <Badge color="teal" variant="light" w="fit-content">Recovery Operations</Badge>
                <Title order={2} c="white">NBFC Recovery OS</Title>
                <Text c="rgba(255,255,255,0.9)">
                  Portfolio-scale collections command center with compliance guardrails, campaign orchestration, and real-time supervisor control.
                </Text>
              </Stack>
            </Stack>
          </BackgroundImage>

          <Paper p="xl" style={{ width: 420, maxWidth: "100%" }}>
            <Stack gap="md">
              <Group justify="space-between">
                <img src={turingEdgeLogo} alt="TuringEdge" style={{ width: 160, objectFit: "contain" }} />
                <Badge variant="outline">Recovery OS</Badge>
              </Group>
              <Stack gap={2}>
                <Title order={2}>Sign in</Title>
                <Text c="dimmed" size="sm">Use your assigned operations credentials.</Text>
              </Stack>

              <form onSubmit={handleSubmit(onSubmit)}>
                <Stack>
                  <TextInput label="Username" placeholder="Enter username" {...register("username")} error={errors.username?.message} />
                  <PasswordInput label="Password" placeholder="Enter password" {...register("password")} error={errors.password?.message} />
                  {errors.root?.message ? (
                    <Text c="red" size="sm">
                      {errors.root.message}
                    </Text>
                  ) : null}
                  <Button type="submit" loading={isSubmitting} leftSection={<ShieldCheck size={16} />}>
                    Login to Recovery OS
                  </Button>
                </Stack>
              </form>

              <Group justify="space-between" mt={4}>
                <Anchor component={Link} to="/forgot-password" size="sm">
                  Forgot password?
                </Anchor>
                {build.data?.demo_mode ? <Badge color="teal">DEMO</Badge> : null}
              </Group>

              {build.data?.demo_mode ? (
                <>
                  <Divider label="Demo Credentials" labelPosition="center" />
                  <Stack gap={4}>
                    <Text size="xs" c="dimmed">`admin/admin123`, `mgr/mgr123`, `agent/agent123`, `ceo/ceo123`, `cfo/cfo123`, `comp/comp123`</Text>
                  </Stack>
                </>
              ) : null}
            </Stack>
          </Paper>
        </Group>
      </Card>
    </Center>
  );
}
