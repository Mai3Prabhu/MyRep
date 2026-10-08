"use client";

function asRecord(value: unknown): Record<string, unknown> | null {
  if (value && typeof value === "object" && !Array.isArray(value)) {
    return value as Record<string, unknown>;
  }
  return null;
}

function pickString(obj: Record<string, unknown>, keys: string[]): string | null {
  for (const key of keys) {
    const value = obj[key];
    if (typeof value === "string" && value.trim()) return value;
  }
  return null;
}

function ItemCard({ item }: { item: unknown }) {
  if (typeof item === "string") {
    return (
      <li className="py-2 text-sm text-[#3D3A45]">
        {item}
      </li>
    );
  }

  const obj = asRecord(item);
  if (!obj) {
    return (
      <li className="py-2 text-sm text-[#3D3A45]">
        {String(item)}
      </li>
    );
  }

  const title = pickString(obj, ["title", "name", "role", "degree", "position"]);
  const org = pickString(obj, [
    "company",
    "organization",
    "school",
    "institution",
    "employer",
  ]);
  const when = pickString(obj, ["dates", "year", "period", "duration", "start"]);
  const description = pickString(obj, [
    "description",
    "summary",
    "details",
    "about",
  ]);
  const tech = obj.tech;

  return (
    <li className="rounded-2xl border border-slate-200/80 bg-white p-5 shadow-2xs hover:border-slate-300 transition-colors">
      <div className="flex flex-col sm:flex-row sm:items-baseline sm:justify-between gap-1">
        {title && (
          <h4 className="text-sm font-bold text-slate-900">{title}</h4>
        )}
        {(org || when) && (
          <p className="text-xs font-medium text-slate-500">
            {[org, when].filter(Boolean).join(" · ")}
          </p>
        )}
      </div>

      {description && (
        <p className="mt-2 text-xs sm:text-sm leading-relaxed text-slate-600">
          {description}
        </p>
      )}

      {Boolean(tech) && (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {(Array.isArray(tech) ? tech : String(tech).split(",")).map((t, ti) => (
            <span
              key={ti}
              className="rounded-lg bg-[#FAF9FD] border border-slate-200 px-2 py-0.5 text-[10px] font-medium text-slate-600"
            >
              {String(t).trim()}
            </span>
          ))}
        </div>
      )}

      {!title && !org && !description && (
        <p className="text-xs text-slate-700">
          {Object.values(obj)
            .filter((v) => typeof v === "string")
            .join(" · ") || "—"}
        </p>
      )}
    </li>
  );
}

export default function PublicSection({
  title,
  items,
  chips,
}: {
  title: string;
  items: unknown[] | null | undefined;
  chips?: boolean;
}) {
  if (!items || items.length === 0) return null;

  if (chips && items.every((item) => typeof item === "string")) {
    return (
      <section className="space-y-3">
        <h3 className="font-display text-2xl text-[#16161D]">{title}</h3>
        <p className="text-sm tracking-wide text-[#6B6574]">{items.map(String).join("  ·  ")}</p>
      </section>
    );
  }

  return (
    <section className="space-y-3">
      <h3 className="font-display text-2xl text-[#16161D]">{title}</h3>
      <ul className="space-y-3">
        {items.map((item, i) => (
          <ItemCard key={i} item={item} />
        ))}
      </ul>
    </section>
  );
}
