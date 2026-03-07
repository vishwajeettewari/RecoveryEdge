import { Badge } from "@mantine/core";

export function SlaBadge({ breach }: { breach?: boolean }) {
  return breach ? (
    <Badge color="red" variant="light">
      SLA BREACH
    </Badge>
  ) : (
    <Badge color="green" variant="light">
      SLA OK
    </Badge>
  );
}
