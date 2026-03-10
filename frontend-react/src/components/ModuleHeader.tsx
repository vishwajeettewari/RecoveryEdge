import { Badge, Group, Paper, Stack, Text, Title } from "@mantine/core";

export function ModuleHeader({
  title,
  subtitle,
  badge,
  action,
}: {
  title: string;
  subtitle?: string;
  badge?: string;
  action?: React.ReactNode;
}) {
  return (
    <Paper className="te-module-header" p="md" radius="lg" withBorder>
      <Group justify="space-between" align="flex-start" wrap="nowrap">
        <Stack gap={4}>
          <Group gap="xs">
            <Title order={3} c="var(--te-heading)" style={{ letterSpacing: "-0.015em" }}>
              {title}
            </Title>
            {badge ? (
              <Badge variant="filled" color="blue">
                {badge}
              </Badge>
            ) : null}
          </Group>
          {subtitle ? (
            <Text size="sm" c="var(--te-copy)" maw={860}>
              {subtitle}
            </Text>
          ) : null}
        </Stack>
        {action || null}
      </Group>
    </Paper>
  );
}
