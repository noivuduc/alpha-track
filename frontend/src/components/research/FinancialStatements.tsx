"use client";
import { useState } from "react";
import { IncomeStatement, BalanceSheet, CashFlowStatement } from "@/lib/api";

function fmtNum(n: number | undefined | null): string {
  if (n == null) return "—";
  const abs = Math.abs(n);
  if (abs >= 1e9) return `${n < 0 ? "-" : ""}$${(abs / 1e9).toFixed(2)}B`;
  if (abs >= 1e6) return `${n < 0 ? "-" : ""}$${(abs / 1e6).toFixed(1)}M`;
  return `$${n.toLocaleString()}`;
}

type Row = { label: string; key: string; indent?: boolean; bold?: boolean };

const INCOME_ROWS: Row[] = [
  { label: "Revenue",              key: "revenue",              bold: true },
  { label: "Cost of Revenue",      key: "cost_of_revenue",      indent: true },
  { label: "Gross Profit",         key: "gross_profit",         bold: true },
  { label: "R&D",                  key: "research_and_development", indent: true },
  { label: "SG&A",                 key: "selling_general_and_administrative_expenses", indent: true },
  { label: "Operating Expense",    key: "operating_expense",    indent: true },
  { label: "Operating Income",     key: "operating_income",     bold: true },
  { label: "EBIT",                 key: "ebit" },
  { label: "Interest Expense",     key: "interest_expense",     indent: true },
  { label: "Income Tax",           key: "income_tax_expense",   indent: true },
  { label: "Net Income",           key: "net_income",           bold: true },
  { label: "EPS (Basic)",          key: "earnings_per_share" },
  { label: "EPS (Diluted)",        key: "earnings_per_share_diluted" },
  { label: "Shares (Diluted, M)",  key: "weighted_average_shares_diluted" },
];

const BALANCE_ROWS: Row[] = [
  { label: "Cash & Equivalents",   key: "cash_and_equivalents",  bold: true },
  { label: "Receivables",          key: "trade_and_non_trade_receivables", indent: true },
  { label: "Inventory",            key: "inventory",              indent: true },
  { label: "Current Assets",       key: "current_assets",         bold: true },
  { label: "PP&E",                 key: "property_plant_and_equipment", indent: true },
  { label: "Goodwill & Intangibles",key: "goodwill_and_intangible_assets", indent: true },
  { label: "Total Assets",         key: "total_assets",           bold: true },
  { label: "Current Debt",         key: "current_debt",           indent: true },
  { label: "Current Liabilities",  key: "current_liabilities",    bold: true },
  { label: "Long-term Debt",       key: "non_current_debt",       indent: true },
  { label: "Total Debt",           key: "total_debt" },
  { label: "Total Liabilities",    key: "total_liabilities",      bold: true },
  { label: "Shareholders' Equity", key: "shareholders_equity",    bold: true },
  { label: "Retained Earnings",    key: "retained_earnings",      indent: true },
  { label: "Shares Outstanding",   key: "outstanding_shares" },
];

const CASHFLOW_ROWS: Row[] = [
  { label: "Net Income",            key: "net_income",             bold: true },
  { label: "D&A",                   key: "depreciation_and_amortization", indent: true },
  { label: "Stock Comp.",           key: "share_based_compensation", indent: true },
  { label: "Operating Cash Flow",   key: "net_cash_flow_from_operations", bold: true },
  { label: "Capex",                 key: "capital_expenditure",    indent: true },
  { label: "Free Cash Flow",        key: "free_cash_flow",         bold: true },
  { label: "Investing Cash Flow",   key: "net_cash_flow_from_investing" },
  { label: "Debt Issuance/Repay",   key: "issuance_or_repayment_of_debt_securities", indent: true },
  { label: "Share Buybacks/Issu.",  key: "issuance_or_purchase_of_equity_shares",    indent: true },
  { label: "Dividends Paid",        key: "dividends_and_other_cash_distributions",   indent: true },
  { label: "Financing Cash Flow",   key: "net_cash_flow_from_financing" },
  { label: "Ending Cash",           key: "ending_cash_balance",    bold: true },
];

function isEpsField(key: string) {
  return key === "earnings_per_share" || key === "earnings_per_share_diluted";
}
function isShareField(key: string) {
  return key === "weighted_average_shares_diluted" || key === "outstanding_shares";
}

function cellFmt(key: string, v: number | undefined | null): string {
  if (v == null) return "—";
  if (isEpsField(key))  return `$${v.toFixed(2)}`;
  if (isShareField(key)) return `${(v / 1e6).toFixed(0)}M`;
  return fmtNum(v);
}

function cellColor(key: string, v: number | undefined | null): string {
  if (v == null) return "text-zinc-500";
  if (isEpsField(key) || key === "net_income" || key === "free_cash_flow" ||
      key === "operating_income" || key === "gross_profit") {
    return v >= 0 ? "text-emerald-400" : "text-red-400";
  }
  return "text-zinc-300";
}

type TabKey = "income" | "balance" | "cashflow";

interface Props {
  income:           IncomeStatement[];
  balance:          BalanceSheet[];
  cashflow:         CashFlowStatement[];
  incomeQ?:         IncomeStatement[];
  balanceQ?:        BalanceSheet[];
  cashflowQ?:       CashFlowStatement[];
  period?:          "annual" | "quarterly";
  onPeriodChange?:  (p: "annual" | "quarterly") => void;
}

export default function FinancialStatements({
  income, balance, cashflow,
  incomeQ = [], balanceQ = [], cashflowQ = [],
  period = "annual", onPeriodChange,
}: Props) {
  const [tab, setTab] = useState<TabKey>("income");
  const isQ = period === "quarterly";

  const activeIncome  = isQ ? incomeQ  : income;
  const activeBalance = isQ ? balanceQ : balance;
  const activeCashflow = isQ ? cashflowQ : cashflow;

  function fmtPeriodLabel(r: { report_period: string; fiscal_period?: string }) {
    if (!isQ) return r.report_period.slice(0, 4);
    const qLabel = r.fiscal_period?.match(/Q\d/)?.[0] || "";
    return `${r.report_period.slice(0, 4)} ${qLabel}`;
  }

  const periods  = activeIncome.map(fmtPeriodLabel);
  const bperiods = activeBalance.map(fmtPeriodLabel);
  const cperiods = activeCashflow.map(fmtPeriodLabel);

  const tabs: { id: TabKey; label: string }[] = [
    { id: "income",   label: "Income Statement" },
    { id: "balance",  label: "Balance Sheet"    },
    { id: "cashflow", label: "Cash Flow"        },
  ];

  function renderTable(
    rows: Row[], data: Record<string, unknown>[], colPeriods: string[]
  ) {
    return (
      <div className="overflow-x-auto scrollbar-thin">
        <table className="w-full text-xs min-w-[700px]">
          <thead>
            <tr className="border-b border-zinc-700">
              <th className="text-left text-zinc-500 py-2 pr-4 font-medium w-48 shrink-0">Metric</th>
              {colPeriods.map(y => (
                <th key={y} className="text-right text-zinc-500 py-2 px-3 font-medium tabular-nums">{y}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map(row => (
              <tr key={row.key} className="border-b border-zinc-800/50 hover:bg-zinc-800/30 transition-colors">
                <td className={`py-2 pr-4 ${row.indent ? "pl-4 text-zinc-500" : ""} ${row.bold ? "text-zinc-200 font-semibold" : "text-zinc-400"}`}>
                  {row.label}
                </td>
                {data.map((rec, i) => {
                  const v = rec[row.key] as number | undefined | null;
                  return (
                    <td key={i} className={`py-2 px-3 text-right font-mono tabular-nums ${row.bold ? cellColor(row.key, v) : "text-zinc-400"}`}>
                      {cellFmt(row.key, v)}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }

  return (
    <div>
      <div className="flex items-center justify-between border-b border-zinc-700 mb-4">
        <div className="flex gap-1">
          {tabs.map(t => (
            <button key={t.id} onClick={() => setTab(t.id)}
              className={`px-4 py-2 text-xs font-medium transition-colors border-b-2 -mb-px ${
                tab === t.id ? "border-blue-500 text-blue-400" : "border-transparent text-zinc-500 hover:text-zinc-300"
              }`}>
              {t.label}
            </button>
          ))}
        </div>
        {onPeriodChange && (
          <div className="flex gap-0.5 bg-zinc-800 rounded-lg p-0.5 mb-1">
            {(["annual", "quarterly"] as const).map(p => (
              <button key={p} onClick={() => onPeriodChange(p)}
                className={`px-3 py-1 text-xs rounded-md font-medium transition-colors ${
                  period === p ? "bg-blue-600 text-white" : "text-zinc-400 hover:text-zinc-200"
                }`}>
                {p === "annual" ? "Annual" : "Quarterly"}
              </button>
            ))}
          </div>
        )}
      </div>
      {tab === "income"   && renderTable(INCOME_ROWS,   activeIncome    as unknown as Record<string, unknown>[], periods)}
      {tab === "balance"  && renderTable(BALANCE_ROWS,  activeBalance   as unknown as Record<string, unknown>[], bperiods)}
      {tab === "cashflow" && renderTable(CASHFLOW_ROWS, activeCashflow  as unknown as Record<string, unknown>[], cperiods)}
    </div>
  );
}
