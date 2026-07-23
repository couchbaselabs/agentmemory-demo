interface Props {
  children: React.ReactNode;
  maxWidth?: number;
}

export default function OpsViewWrapper({ children, maxWidth }: Props) {
  return (
    <div style={{
      width: "100%",
      maxWidth: maxWidth ?? "100%",
      padding: "2rem 2.5rem",
      display: "flex",
      flexDirection: "column",
      gap: "1.5rem",
      boxSizing: "border-box",
    }}>
      {children}
    </div>
  );
}
