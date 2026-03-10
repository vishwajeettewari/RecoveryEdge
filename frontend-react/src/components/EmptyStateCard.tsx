import { Card, Stack, Text, Title } from "@mantine/core";
import { Inbox } from "lucide-react";

export function EmptyStateCard({ title, description }: { title: string; description: string }) {
  return (
    <Card className="te-empty-state">
      <Stack align="center" py="xl" gap="xs">
        <Inbox size={30} color="var(--te-empty-icon)" />
        <Title order={4}>{title}</Title>
        <Text size="sm" c="dimmed" ta="center" maw={460}>
          {description}
        </Text>
      </Stack>
    </Card>
  );
}
