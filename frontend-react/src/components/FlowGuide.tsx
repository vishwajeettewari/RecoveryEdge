import { Card, Group, SimpleGrid, Stack, Text, ThemeIcon } from "@mantine/core";
import { ArrowRight } from "lucide-react";

export interface FlowStep {
  title: string;
  detail: string;
}

export function FlowGuide({
  title = "How This Works",
  steps,
}: {
  title?: string;
  steps: FlowStep[];
}) {
  return (
    <Card className="te-flow-guide" withBorder>
      <Stack gap="sm">
        <Text fw={700} size="sm" c="#5f6671" tt="uppercase" style={{ letterSpacing: "0.08em" }}>
          {title}
        </Text>
        <SimpleGrid cols={{ base: 1, md: Math.min(steps.length, 4) }}>
          {steps.map((step, idx) => (
            <Group key={`${step.title}-${idx}`} align="flex-start" wrap="nowrap" className="te-flow-step">
              <ThemeIcon radius="xl" size={28} variant="filled" className="te-flow-number">
                {idx + 1}
              </ThemeIcon>
              <Stack gap={2}>
                <Group gap={6}>
                  <Text fw={700} size="sm" c="#17181b">
                    {step.title}
                  </Text>
                  {idx < steps.length - 1 ? <ArrowRight size={13} color="#8fb8ff" /> : null}
                </Group>
                <Text size="xs" c="#6f7784">
                  {step.detail}
                </Text>
              </Stack>
            </Group>
          ))}
        </SimpleGrid>
      </Stack>
    </Card>
  );
}
