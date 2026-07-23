import type { GuestUser } from "@/lib/types";

interface Props {
  user: GuestUser;
  active?: boolean;
}

export default function PersonaCard({ user, active }: Props) {
  return (
    <div className={`persona-card${active ? " active" : ""}`} style={{ cursor: "default" }}>
      <span className="persona-name">{user.name}</span>
    </div>
  );
}
