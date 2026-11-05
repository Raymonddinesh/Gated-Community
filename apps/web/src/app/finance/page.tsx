"use client";

import React, { useState, useEffect } from "react";
import { apiClient } from "@/lib/api-client";

// Internationalization Dictionaries (English & Tamil)
const i18n = {
  en: {
    title: "Financial Accounting Core",
    subtitle: "Immutable double-entry general ledger, chart of accounts, financial statements, and auditing.",
    easyMode: "Easy Mode",
    standardMode: "Standard Mode",
    adminMode: "Admin Mode",
    language: "Language",
    english: "English",
    tamil: "தமிழ்",
    tabs: {
      dashboard: "Financial Summary",
      accounts: "Chart of Accounts",
      journals: "Journal Entries",
      reports: "Financial Statements",
      periods: "Financial Periods",
    },
    metrics: {
      totalCashBank: "Total Cash & Bank",
      monthlyIncome: "Monthly Income",
      monthlyExpenses: "Monthly Expenses",
      netSurplus: "Net Operating Surplus",
    },
    buttons: {
      newJournal: "+ Post Journal Entry",
      newAccount: "+ Add Account",
      generateReport: "Generate Report",
      closePeriod: "Close Financial Period",
    },
    table: {
      code: "Account Code",
      name: "Account Name",
      type: "Type",
      balance: "Balance (₹)",
      status: "Status",
    },
  },
  ta: {
    title: "நிதி கணக்கியல் மையம்",
    subtitle: "இரட்டை பதிவு பொது பேரேடு, கணக்குகள் வரைபடம் மற்றும் நிதி அறிக்கைகள்.",
    easyMode: "எளிதான பயன்முறை",
    standardMode: "சாதாரண பயன்முறை",
    adminMode: "நிர்வாகி பயன்முறை",
    language: "மொழி",
    english: "English",
    tamil: "தமிழ்",
    tabs: {
      dashboard: "நிதி சுருக்கம்",
      accounts: "கணக்குகள் வரைபடம்",
      journals: "குறிப்பேடு பதிவுகள்",
      reports: "நிதி அறிக்கைகள்",
      periods: "நிதி காலங்கள்",
    },
    metrics: {
      totalCashBank: "மொத்த ரொக்கம் & வங்கி",
      monthlyIncome: "மாதாந்திர வருமானம்",
      monthlyExpenses: "மாதாந்திர செலவுகள்",
      netSurplus: "நிகர உபரி",
    },
    buttons: {
      newJournal: "+ குறிப்பேடு பதிவு செய்",
      newAccount: "+ கணக்கு சேர்",
      generateReport: "அறிக்கை உருவாக்கு",
      closePeriod: "நிதி காலத்தை மூடு",
    },
    table: {
      code: "கணக்கு குறியீடு",
      name: "கணக்கு பெயர்",
      type: "வகை",
      balance: "இருப்பு (₹)",
      status: "நிலை",
    },
  },
};

const initialAccounts = [
  { code: "1010", name: "Axis Bank Operating Account", type: "ASSET", balance: 1450000.0, status: "ACTIVE" },
  { code: "1020", name: "Petty Cash", type: "ASSET", balance: 25000.0, status: "ACTIVE" },
  { code: "2010", name: "Accounts Payable - Vendors", type: "LIABILITY", balance: 85000.0, status: "ACTIVE" },
  { code: "3010", name: "General Operating Fund", type: "EQUITY", balance: 1200000.0, status: "ACTIVE" },
  { code: "4010", name: "Maintenance Collection Income", type: "REVENUE", balance: 450000.0, status: "ACTIVE" },
  { code: "5010", name: "Security & Guarding Services", type: "EXPENSE", balance: 180000.0, status: "ACTIVE" },
  { code: "5020", name: "Common Area Electricity", type: "EXPENSE", balance: 65000.0, status: "ACTIVE" },
];

export default function FinancePage() {
  const [lang, setLang] = useState<"en" | "ta">("en");
  const [mode, setMode] = useState<"EASY" | "STANDARD" | "ADMIN">("STANDARD");
  const [activeTab, setActiveTab] = useState<"dashboard" | "accounts" | "journals" | "reports" | "periods">("dashboard");
  const [accounts, setAccounts] = useState(initialAccounts);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const t = i18n[lang];

  useEffect(() => {
    async function fetchAccounts() {
      try {
        setLoading(true);
        const data = await apiClient<Array<{
          code: string;
          name: string;
          type: string;
          balance: number;
          status: string;
        }>>('/api/v1/finance/accounts');

        if (data && Array.isArray(data)) {
          setAccounts(data);
        }
      } catch (err: unknown) {
        setError(err instanceof Error ? err.message : 'Finance API unavailable');
      } finally {
        setLoading(false);
      }
    }
    fetchAccounts();
  }, []);

  return (
    <div style={{ padding: "24px", maxWidth: "1200px", margin: "0 auto", fontFamily: "system-ui, sans-serif" }}>
      {/* Header & Controls */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "20px" }}>
        <div>
          <h1 style={{ fontSize: "28px", fontWeight: "bold", margin: 0 }}>{t.title}</h1>
          <p style={{ color: "#666", margin: "4px 0 0 0" }}>{t.subtitle}</p>
        </div>

        <div style={{ display: "flex", gap: "12px", alignItems: "center" }}>
          {/* Mode Switcher */}
          <div style={{ background: "#eee", padding: "4px", borderRadius: "8px", display: "flex" }}>
            <button
              onClick={() => setMode("EASY")}
              style={{
                padding: "6px 12px",
                border: "none",
                borderRadius: "6px",
                cursor: "pointer",
                fontWeight: mode === "EASY" ? "bold" : "normal",
                background: mode === "EASY" ? "#2563eb" : "transparent",
                color: mode === "EASY" ? "#fff" : "#333",
              }}
            >
              {t.easyMode}
            </button>
            <button
              onClick={() => setMode("STANDARD")}
              style={{
                padding: "6px 12px",
                border: "none",
                borderRadius: "6px",
                cursor: "pointer",
                fontWeight: mode === "STANDARD" ? "bold" : "normal",
                background: mode === "STANDARD" ? "#2563eb" : "transparent",
                color: mode === "STANDARD" ? "#fff" : "#333",
              }}
            >
              {t.standardMode}
            </button>
            <button
              onClick={() => setMode("ADMIN")}
              style={{
                padding: "6px 12px",
                border: "none",
                borderRadius: "6px",
                cursor: "pointer",
                fontWeight: mode === "ADMIN" ? "bold" : "normal",
                background: mode === "ADMIN" ? "#2563eb" : "transparent",
                color: mode === "ADMIN" ? "#fff" : "#333",
              }}
            >
              {t.adminMode}
            </button>
          </div>

          {/* Language Switcher */}
          <select
            value={lang}
            onChange={(e) => setLang(e.target.value as "en" | "ta")}
            style={{ padding: "6px 12px", borderRadius: "6px", border: "1px solid #ccc" }}
          >
            <option value="en">{t.english}</option>
            <option value="ta">{t.tamil}</option>
          </select>
        </div>
      </div>

      {/* EASY MODE UI */}
      {mode === "EASY" && (
        <div style={{ background: "#f8fafc", border: "2px solid #cbd5e1", borderRadius: "12px", padding: "24px" }}>
          <h2 style={{ fontSize: "22px", marginTop: 0 }}>Financial Overview (Simple View)</h2>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: "16px", marginTop: "16px" }}>
            <div style={{ background: "#fff", border: "1px solid #cbd5e1", padding: "20px", borderRadius: "8px" }}>
              <div style={{ fontSize: "14px", color: "#64748b" }}>{t.metrics.totalCashBank}</div>
              <div style={{ fontSize: "28px", fontWeight: "bold", color: "#16a34a", marginTop: "8px" }}>
                ₹14,75,000.00
              </div>
            </div>
            <div style={{ background: "#fff", border: "1px solid #cbd5e1", padding: "20px", borderRadius: "8px" }}>
              <div style={{ fontSize: "14px", color: "#64748b" }}>{t.metrics.netSurplus}</div>
              <div style={{ fontSize: "28px", fontWeight: "bold", color: "#2563eb", marginTop: "8px" }}>
                ₹2,05,000.00
              </div>
            </div>
          </div>
        </div>
      )}

      {/* STANDARD & ADMIN MODES UI */}
      {mode !== "EASY" && (
        <div>
          {/* Navigation Tabs */}
          <div style={{ display: "flex", gap: "8px", borderBottom: "2px solid #e2e8f0", marginBottom: "20px" }}>
            <button
              onClick={() => setActiveTab("dashboard")}
              style={{
                padding: "12px 20px",
                border: "none",
                borderBottom: activeTab === "dashboard" ? "3px solid #2563eb" : "none",
                background: "transparent",
                fontWeight: activeTab === "dashboard" ? "bold" : "normal",
                cursor: "pointer",
              }}
            >
              {t.tabs.dashboard}
            </button>
            <button
              onClick={() => setActiveTab("accounts")}
              style={{
                padding: "12px 20px",
                border: "none",
                borderBottom: activeTab === "accounts" ? "3px solid #2563eb" : "none",
                background: "transparent",
                fontWeight: activeTab === "accounts" ? "bold" : "normal",
                cursor: "pointer",
              }}
            >
              {t.tabs.accounts}
            </button>

            {mode === "ADMIN" && (
              <>
                <button
                  onClick={() => setActiveTab("journals")}
                  style={{
                    padding: "12px 20px",
                    border: "none",
                    borderBottom: activeTab === "journals" ? "3px solid #2563eb" : "none",
                    background: "transparent",
                    fontWeight: activeTab === "journals" ? "bold" : "normal",
                    cursor: "pointer",
                  }}
                >
                  {t.tabs.journals}
                </button>
                <button
                  onClick={() => setActiveTab("reports")}
                  style={{
                    padding: "12px 20px",
                    border: "none",
                    borderBottom: activeTab === "reports" ? "3px solid #2563eb" : "none",
                    background: "transparent",
                    fontWeight: activeTab === "reports" ? "bold" : "normal",
                    cursor: "pointer",
                  }}
                >
                  {t.tabs.reports}
                </button>
                <button
                  onClick={() => setActiveTab("periods")}
                  style={{
                    padding: "12px 20px",
                    border: "none",
                    borderBottom: activeTab === "periods" ? "3px solid #2563eb" : "none",
                    background: "transparent",
                    fontWeight: activeTab === "periods" ? "bold" : "normal",
                    cursor: "pointer",
                  }}
                >
                  {t.tabs.periods}
                </button>
              </>
            )}
          </div>

          {/* Dashboard Tab */}
          {activeTab === "dashboard" && (
            <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: "16px" }}>
              <div style={{ background: "#fff", border: "1px solid #cbd5e1", borderRadius: "8px", padding: "16px" }}>
                <div style={{ fontSize: "14px", color: "#64748b" }}>{t.metrics.totalCashBank}</div>
                <div style={{ fontSize: "24px", fontWeight: "bold", color: "#0f172a", marginTop: "8px" }}>
                  ₹14,75,000.00
                </div>
              </div>
              <div style={{ background: "#fff", border: "1px solid #cbd5e1", borderRadius: "8px", padding: "16px" }}>
                <div style={{ fontSize: "14px", color: "#64748b" }}>{t.metrics.monthlyIncome}</div>
                <div style={{ fontSize: "24px", fontWeight: "bold", color: "#16a34a", marginTop: "8px" }}>
                  ₹4,50,000.00
                </div>
              </div>
              <div style={{ background: "#fff", border: "1px solid #cbd5e1", borderRadius: "8px", padding: "16px" }}>
                <div style={{ fontSize: "14px", color: "#64748b" }}>{t.metrics.monthlyExpenses}</div>
                <div style={{ fontSize: "24px", fontWeight: "bold", color: "#dc2626", marginTop: "8px" }}>
                  ₹2,45,000.00
                </div>
              </div>
              <div style={{ background: "#fff", border: "1px solid #cbd5e1", borderRadius: "8px", padding: "16px" }}>
                <div style={{ fontSize: "14px", color: "#64748b" }}>{t.metrics.netSurplus}</div>
                <div style={{ fontSize: "24px", fontWeight: "bold", color: "#2563eb", marginTop: "8px" }}>
                  ₹2,05,000.00
                </div>
              </div>
            </div>
          )}

          {/* Chart of Accounts Tab */}
          {activeTab === "accounts" && (
            <div style={{ background: "#fff", border: "1px solid #cbd5e1", borderRadius: "8px", padding: "20px" }}>
              <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "16px" }}>
                <h3 style={{ margin: 0 }}>Society General Ledger Accounts</h3>
                {mode === "ADMIN" && (
                  <button
                    style={{
                      padding: "8px 16px",
                      background: "#2563eb",
                      color: "#fff",
                      border: "none",
                      borderRadius: "6px",
                      cursor: "pointer",
                    }}
                  >
                    {t.buttons.newAccount}
                  </button>
                )}
              </div>
              <table style={{ width: "100%", borderCollapse: "collapse", textAlign: "left" }}>
                <thead>
                  <tr style={{ background: "#f1f5f9" }}>
                    <th style={{ padding: "10px", borderBottom: "1px solid #cbd5e1" }}>{t.table.code}</th>
                    <th style={{ padding: "10px", borderBottom: "1px solid #cbd5e1" }}>{t.table.name}</th>
                    <th style={{ padding: "10px", borderBottom: "1px solid #cbd5e1" }}>{t.table.type}</th>
                    <th style={{ padding: "10px", borderBottom: "1px solid #cbd5e1" }}>{t.table.balance}</th>
                    <th style={{ padding: "10px", borderBottom: "1px solid #cbd5e1" }}>{t.table.status}</th>
                  </tr>
                </thead>
                <tbody>
                  {accounts.map((acc) => (
                    <tr key={acc.code}>
                      <td style={{ padding: "10px", borderBottom: "1px solid #e2e8f0" }}>{acc.code}</td>
                      <td style={{ padding: "10px", borderBottom: "1px solid #e2e8f0" }}>{acc.name}</td>
                      <td style={{ padding: "10px", borderBottom: "1px solid #e2e8f0" }}>{acc.type}</td>
                      <td style={{ padding: "10px", borderBottom: "1px solid #e2e8f0", fontWeight: "bold" }}>
                        ₹{acc.balance.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                      </td>
                      <td style={{ padding: "10px", borderBottom: "1px solid #e2e8f0", color: "green" }}>{acc.status}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* Reports Tab */}
          {activeTab === "reports" && mode === "ADMIN" && (
            <div style={{ background: "#fff", border: "1px solid #cbd5e1", borderRadius: "8px", padding: "20px" }}>
              <h3 style={{ marginTop: 0 }}>Financial Statements & Audit Snapshots</h3>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: "16px", marginTop: "16px" }}>
                <div style={{ border: "1px solid #cbd5e1", borderRadius: "6px", padding: "16px" }}>
                  <strong>Income & Expenditure Statement</strong>
                  <p style={{ color: "#64748b", fontSize: "14px" }}>Operational income vs expenses for active period.</p>
                  <button style={{ padding: "6px 12px", background: "#2563eb", color: "#fff", border: "none", borderRadius: "4px" }}>
                    View Statement
                  </button>
                </div>
                <div style={{ border: "1px solid #cbd5e1", borderRadius: "6px", padding: "16px" }}>
                  <strong>Balance Sheet</strong>
                  <p style={{ color: "#64748b", fontSize: "14px" }}>Assets, liabilities, and equity balances.</p>
                  <button style={{ padding: "6px 12px", background: "#2563eb", color: "#fff", border: "none", borderRadius: "4px" }}>
                    View Statement
                  </button>
                </div>
                <div style={{ border: "1px solid #cbd5e1", borderRadius: "6px", padding: "16px" }}>
                  <strong>Trial Balance</strong>
                  <p style={{ color: "#64748b", fontSize: "14px" }}>General ledger debit and credit verification.</p>
                  <button style={{ padding: "6px 12px", background: "#2563eb", color: "#fff", border: "none", borderRadius: "4px" }}>
                    View Statement
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
