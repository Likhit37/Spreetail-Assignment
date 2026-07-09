// Small presentational helpers shared across pages.

export const inr = (v) =>
  `₹${Number(v).toLocaleString("en-IN", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;

// Deterministic pleasant color from a name (for avatars).
function hue(name) {
  let h = 0;
  for (let i = 0; i < (name || "").length; i++) h = (h * 31 + name.charCodeAt(i)) % 360;
  return h;
}

export function initials(name = "") {
  const parts = name.replace(/[^a-zA-Z ]/g, "").trim().split(/\s+/);
  return ((parts[0]?.[0] || "?") + (parts[1]?.[0] || "")).toUpperCase();
}

export function Avatar({ name, sm }) {
  const h = hue(name);
  return (
    <span
      className={`avatar${sm ? " sm" : ""}`}
      style={{
        background: `linear-gradient(135deg, hsl(${h} 70% 55%), hsl(${(h + 40) % 360} 70% 45%))`,
      }}
      title={name}
    >
      {initials(name)}
    </span>
  );
}
