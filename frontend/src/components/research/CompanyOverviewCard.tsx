"use client";
import { useState } from "react";
import { X } from "lucide-react";

interface Company {
  name?:     string;
  sector?:   string;
  industry?: string;
  exchange?: string;
  location?: string;
  cik?:      string;
}
interface Profile {
  description?:    string;
  employees?:      number | null;
  market_cap?:     number | null;
  enterprise_value?: number | null;
  website?:        string;
  currency?:       string;
  country?:        string;
  officers?:       { name: string; title: string; pay?: number | null }[];
}

interface Props {
  company: Company;
  profile: Profile;
}

function fmtLarge(n: number | null | undefined): string {
  if (n == null) return "—";
  if (Math.abs(n) >= 1e12) return `$${(n / 1e12).toFixed(2)}T`;
  if (Math.abs(n) >= 1e9)  return `$${(n / 1e9).toFixed(2)}B`;
  if (Math.abs(n) >= 1e6)  return `$${(n / 1e6).toFixed(1)}M`;
  return `$${n.toLocaleString()}`;
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-[10px] text-zinc-600 uppercase tracking-wider mb-0.5">{label}</div>
      <div className="text-xs text-zinc-300 font-medium leading-snug">{value}</div>
    </div>
  );
}

export default function CompanyOverviewCard({ company, profile }: Props) {
  const [modalOpen, setModalOpen] = useState(false);

  const hasDescription = !!profile.description;
  const hasAnyFact = !!(
    company.sector || company.industry || company.exchange ||
    (company.location || profile.country) || profile.employees || profile.market_cap
  );

  if (!hasDescription && !hasAnyFact) return null;

  return (
    <>
      {/* ── Card ──────────────────────────────────────────────────── */}
      <div className="bg-zinc-900/60 border border-zinc-800/60 rounded-xl p-4 flex flex-col h-full gap-3">
        <div className="text-xs font-semibold text-zinc-400 uppercase tracking-wider">Company Overview</div>

        {/* Description preview — clamped, grows to fill space */}
        {hasDescription && (
          <div className="flex-1 flex flex-col gap-1.5 min-h-0">
            <p className="text-sm text-zinc-400 leading-relaxed line-clamp-4">
              {profile.description}
            </p>
            <button
              onClick={() => setModalOpen(true)}
              className="text-[11px] text-blue-500 hover:text-blue-400 transition-colors self-start"
            >
              Read more
            </button>
          </div>
        )}

        {/* Compact facts grid — sits at bottom */}
        {hasAnyFact && (
          <div className="grid grid-cols-2 gap-x-4 gap-y-2.5 pt-2 border-t border-zinc-800/40 mt-auto">
            {company.sector           && <Fact label="Sector"     value={company.sector} />}
            {company.industry         && <Fact label="Industry"   value={company.industry} />}
            {company.exchange         && <Fact label="Exchange"   value={company.exchange} />}
            {(company.location || profile.country) && (
              <Fact label="Location" value={company.location ?? profile.country ?? ""} />
            )}
            {profile.employees        && <Fact label="Employees"  value={profile.employees.toLocaleString()} />}
            {profile.market_cap       && <Fact label="Market Cap" value={fmtLarge(profile.market_cap)} />}
          </div>
        )}
      </div>

      {/* ── Modal ─────────────────────────────────────────────────── */}
      {modalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          {/* Backdrop */}
          <div
            className="absolute inset-0 bg-black/70"
            onClick={() => setModalOpen(false)}
          />

          {/* Panel */}
          <div className="relative bg-zinc-900 border border-zinc-800 rounded-2xl shadow-2xl w-full max-w-2xl max-h-[80vh] flex flex-col">
            {/* Modal header */}
            <div className="flex items-center justify-between px-5 py-4 border-b border-zinc-800 shrink-0">
              <div>
                <div className="text-sm font-semibold text-zinc-100">{company.name ?? "Company"}</div>
                {(company.sector || company.industry) && (
                  <div className="text-xs text-zinc-500 mt-0.5">
                    {[company.sector, company.industry].filter(Boolean).join(" · ")}
                  </div>
                )}
              </div>
              <button
                onClick={() => setModalOpen(false)}
                className="text-zinc-500 hover:text-zinc-200 transition-colors"
              >
                <X size={18} />
              </button>
            </div>

            {/* Modal body — scrollable */}
            <div className="overflow-y-auto p-5 space-y-5">
              {/* Full description */}
              {profile.description && (
                <p className="text-sm text-zinc-300 leading-relaxed whitespace-pre-line">
                  {profile.description}
                </p>
              )}

              {/* Extended facts */}
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
                {company.exchange         && (
                  <div className="bg-zinc-800/40 rounded-lg p-3">
                    <div className="text-[10px] text-zinc-500 mb-1">Exchange</div>
                    <div className="text-sm text-zinc-200 font-medium">{company.exchange}</div>
                  </div>
                )}
                {(company.location || profile.country) && (
                  <div className="bg-zinc-800/40 rounded-lg p-3">
                    <div className="text-[10px] text-zinc-500 mb-1">Location</div>
                    <div className="text-sm text-zinc-200 font-medium">{company.location ?? profile.country}</div>
                  </div>
                )}
                {profile.employees && (
                  <div className="bg-zinc-800/40 rounded-lg p-3">
                    <div className="text-[10px] text-zinc-500 mb-1">Employees</div>
                    <div className="text-sm text-zinc-200 font-medium">{profile.employees.toLocaleString()}</div>
                  </div>
                )}
                {profile.market_cap && (
                  <div className="bg-zinc-800/40 rounded-lg p-3">
                    <div className="text-[10px] text-zinc-500 mb-1">Market Cap</div>
                    <div className="text-sm text-zinc-200 font-medium">{fmtLarge(profile.market_cap)}</div>
                  </div>
                )}
                {profile.enterprise_value && (
                  <div className="bg-zinc-800/40 rounded-lg p-3">
                    <div className="text-[10px] text-zinc-500 mb-1">Enterprise Value</div>
                    <div className="text-sm text-zinc-200 font-medium">{fmtLarge(profile.enterprise_value)}</div>
                  </div>
                )}
                {profile.currency && (
                  <div className="bg-zinc-800/40 rounded-lg p-3">
                    <div className="text-[10px] text-zinc-500 mb-1">Currency</div>
                    <div className="text-sm text-zinc-200 font-medium">{profile.currency}</div>
                  </div>
                )}
                {profile.website && (
                  <div className="bg-zinc-800/40 rounded-lg p-3">
                    <div className="text-[10px] text-zinc-500 mb-1">Website</div>
                    <a
                      href={profile.website}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-xs text-blue-400 hover:underline break-all"
                    >
                      {profile.website.replace(/^https?:\/\//, "")}
                    </a>
                  </div>
                )}
                {company.cik && (
                  <div className="bg-zinc-800/40 rounded-lg p-3">
                    <div className="text-[10px] text-zinc-500 mb-1">CIK</div>
                    <div className="text-sm text-zinc-200 font-medium">{company.cik}</div>
                  </div>
                )}
              </div>

              {/* Key Executives */}
              {profile.officers && profile.officers.length > 0 && (
                <div>
                  <div className="text-xs font-semibold text-zinc-400 mb-3">Key Executives</div>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                    {profile.officers.map((o, i) => (
                      <div key={i} className="bg-zinc-800/40 rounded-lg px-3 py-2">
                        <div className="text-sm text-zinc-200 font-medium">{o.name}</div>
                        <div className="text-xs text-zinc-500">{o.title}</div>
                        {o.pay && (
                          <div className="text-xs text-zinc-600 mt-0.5">
                            Comp: ${(o.pay / 1e6).toFixed(1)}M
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </>
  );
}
