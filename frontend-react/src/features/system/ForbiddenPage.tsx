import { Button, Card, Center, Stack, Text, Title } from "@mantine/core";
import { ShieldX } from "lucide-react";
import { Link } from "react-router-dom";

export function ForbiddenPage() {
  return (
    <Center py="xl">
      <Card maw={560} w="100%" withBorder>
        <Stack align="center" ta="center">
          <ShieldX size={36} />
          <Title order={2}>Access Denied</Title>
          <Text c="dimmed">Your role does not have permission to access this screen.</Text>
          <Button component={Link} to="/app">Go back</Button>
        </Stack>
      </Card>
    </Center>
  );
}
