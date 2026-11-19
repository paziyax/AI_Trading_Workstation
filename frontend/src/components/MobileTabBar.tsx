export type MobileTab = "watchlist" | "chart" | "portfolio" | "chat";

const TABS: Array<{ id: MobileTab; label: string }> = [
  { id: "watchlist", label: "Watchlist" },
  { id: "chart", label: "Chart" },
  { id: "portfolio", label: "Portfolio" },
  { id: "chat", label: "Chat" },
];

export function MobileTabBar({
  active,
  onChange,
}: {
  active: MobileTab;
  onChange: (tab: MobileTab) => void;
}) {
  return (
    <nav className="mobile-tabbar" aria-label="Terminal sections">
      {TABS.map((tab) => (
        <button
          key={tab.id}
          type="button"
          className="mobile-tab"
          data-testid={`mobile-tab-${tab.id}`}
          aria-current={active === tab.id ? "true" : undefined}
          onClick={() => onChange(tab.id)}
        >
          {tab.label}
        </button>
      ))}
    </nav>
  );
}
