interface Props {
  tier: string;
  tierClass?: string;
}

const CLASS_MAP: Record<string, string> = {
  "tier-platinum": "tier-platinum",
  "tier-gold": "tier-gold",
  "tier-silver": "tier-silver",
};

export default function TierBadge({ tier, tierClass }: Props) {
  const cls = (tierClass && CLASS_MAP[tierClass]) || `tier-${tier.toLowerCase()}`;
  return <span className={`tier-badge ${cls}`}>{tier}</span>;
}
