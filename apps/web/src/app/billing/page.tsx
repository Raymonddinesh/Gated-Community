"use client";

import React, { useState, useEffect } from "react";
import { apiClient } from "@/lib/api-client";

// Internationalization Dictionaries (English & Tamil)
const i18n = {
  en: {
    title: "Maintenance Billing & Obligations",
    subtitle: "Automated billing rules, period cycles, resident invoices, payments, and account balances.",
    easyMode: "Easy Mode",
    standardMode: "Standard Mode",
    adminMode: "Admin Mode",
    language: "Language",
    english: "English",
    tamil: "தமிழ்",
    tabs: {
      invoices: "Invoices & Balance",
      rules: "Billing Charge Rules",
      periods: "Billing Periods",
      payments: "Payment History",
      config: "Billing Config",
    },
    metrics: {
      totalBilled: "Total Billed (Current Period)",
      totalCollected: "Total Collected",
      outstandingDues: "Outstanding Dues",
      collectionRate: "Collection Rate",
    },
    buttons: {
      generateInvoices: "+ Execute Billing Cycle",
      recordPayment: "+ Record Payment",
      downloadReceipt: "Download Receipt",
      newRule: "+ Create Charge Rule",
    },
    table: {
      invoiceNo: "Invoice #",
      unit: "Unit / Owner",
      amount: "Amount (₹)",
      dueDate: "Due Date",
      status: "Status",
    },
  },
  ta: {
    title: "பராமரிப்பு கட்டணம் & பொறுப்புகள்",
    subtitle: "தானியங்கி கட்டண விதிகள், கால சுழற்சிகள், விலைப்பட்டியல் மற்றும் செலுத்தல் மேலாண்மை.",
    easyMode: "எளிதான பயன்முறை",
    standardMode: "சாதாரண பயன்முறை",
    adminMode: "நிர்வாகி பயன்முறை",
    language: "மொழி",
    english: "English",
    tamil: "தமிழ்",
    tabs: {
      invoices: "விலைப்பட்டியல் & இருப்பு",
      rules: "கட்டண விதிகள்",
      periods: "கட்டண காலங்கள்",
      payments: "செலுத்தல் வரலாறு",
      config: "அமைப்புகள்",
    },
    metrics: {
      totalBilled: "மொத்த கட்டணம் (நடப்பு காலம்)",
      totalCollected: "வசூலிக்கப்பட்ட தொகை",
      outstandingDues: "நிலுவை தொகை",
      collectionRate: "வசூல் சதவீதம்",
    },
    buttons: {
      generateInvoices: "+ கட்டண சுழற்சியை செயல்படுத்து",
      recordPayment: "+ செலுத்துதல் பதிவுசெய்",
      downloadReceipt: "ரசீது பதிவிறக்கு",
      newRule: "+ புதிய விதி சேர்",
    },
    table: {
      invoiceNo: "விலைப்பட்டியல் எண்",
      unit: "அலகு / உரிமையாளர்",
      amount: "தொகை (₹)",
      dueDate: "கடைசி நாள்",
      status: "நிலை",
    },
  },
};

const initialInvoices = [
  { invoiceNo: "INV-202610-001", unit: "Unit A-101 (R. Sharma)", amount: 3500.0, dueDate: "2026-10-15", status: "UNPAID" },
  { invoiceNo: "INV-202610-002", unit: "Unit A-102 (K. Raman)", amount: 3500.0, dueDate: "2026-10-15", status: "PAID" },
  { invoiceNo: "INV-202610-003", unit: "Unit B-201 (S. Menon)", amount: 4200.0, dueDate: "2026-10-15", status: "PAID" },
  { invoiceNo: "INV-202610-004", unit: "Unit B-202 (M. Patel)", amount: 3500.0, dueDate: "2026-10-15", status: "UNPAID" },
];

export default function BillingPage() {
  const [lang, setLang] = useState<"en" | "ta">("en");
  const [mode, setMode] = useState<"EASY" | "STANDARD" | "ADMIN">("STANDARD");
  const [activeTab, setActiveTab] = useState<"invoices" | "rules" | "periods" | "payments" | "config">("invoices");
  const [invoices, setInvoices] = useState(initialInvoices);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const t = i18n[lang];

  useEffect(() => {
    async function fetchInvoices() {
      try {
        setLoading(true);
        const data = await apiClient<Array<{
          invoice_number: string;
          unit_id: string;
          total_amount: number;
          due_date: string;
          status: string;
        }>>('/api/v1/billing/invoices');

        if (data && Array.isArray(data)) {
          setInvoices(data.map(inv => ({
            invoiceNo: inv.invoice_number,
            unit: inv.unit_id,
            amount: inv.total_amount,
            dueDate: inv.due_date,
            status: inv.status,
          })));
        }
      } catch (err: unknown) {
        setError(err instanceof Error ? err.message : 'Billing API unavailable');
      } finally {
        setLoading(false);
      }
    }
    fetchInvoices();
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
          <h2 style={{ fontSize: "22px", marginTop: 0 }}>My Maintenance Invoice</h2>
          <div style={{ background: "#fff", border: "1px solid #cbd5e1", padding: "24px", borderRadius: "8px" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <div>
                <span style={{ background: "#fee2e2", color: "#991b1b", padding: "4px 10px", borderRadius: "4px", fontSize: "14px", fontWeight: "bold" }}>
                  UNPAID
                </span>
                <h3 style={{ fontSize: "24px", margin: "12px 0 4px 0" }}>October 2026 Maintenance Bill</h3>
                <p style={{ color: "#64748b", margin: 0 }}>Invoice #INV-202610-001 • Due Date: Oct 15, 2026</p>
              </div>
              <div style={{ textAlign: "right" }}>
                <div style={{ fontSize: "32px", fontWeight: "bold", color: "#0f172a" }}>₹3,500.00</div>
                <button style={{ marginTop: "12px", padding: "10px 24px", background: "#16a34a", color: "#fff", fontSize: "16px", fontWeight: "bold", border: "none", borderRadius: "6px", cursor: "pointer" }}>
                  Pay Now
                </button>
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
              onClick={() => setActiveTab("invoices")}
              style={{
                padding: "12px 20px",
                border: "none",
                borderBottom: activeTab === "invoices" ? "3px solid #2563eb" : "none",
                background: "transparent",
                fontWeight: activeTab === "invoices" ? "bold" : "normal",
                cursor: "pointer",
              }}
            >
              {t.tabs.invoices}
            </button>

            {mode === "ADMIN" && (
              <>
                <button
                  onClick={() => setActiveTab("rules")}
                  style={{
                    padding: "12px 20px",
                    border: "none",
                    borderBottom: activeTab === "rules" ? "3px solid #2563eb" : "none",
                    background: "transparent",
                    fontWeight: activeTab === "rules" ? "bold" : "normal",
                    cursor: "pointer",
                  }}
                >
                  {t.tabs.rules}
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
                <button
                  onClick={() => setActiveTab("payments")}
                  style={{
                    padding: "12px 20px",
                    border: "none",
                    borderBottom: activeTab === "payments" ? "3px solid #2563eb" : "none",
                    background: "transparent",
                    fontWeight: activeTab === "payments" ? "bold" : "normal",
                    cursor: "pointer",
                  }}
                >
                  {t.tabs.payments}
                </button>
                <button
                  onClick={() => setActiveTab("config")}
                  style={{
                    padding: "12px 20px",
                    border: "none",
                    borderBottom: activeTab === "config" ? "3px solid #2563eb" : "none",
                    background: "transparent",
                    fontWeight: activeTab === "config" ? "bold" : "normal",
                    cursor: "pointer",
                  }}
                >
                  {t.tabs.config}
                </button>
              </>
            )}
          </div>

          {/* Metrics Summary (Admin Mode) */}
          {mode === "ADMIN" && (
            <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: "16px", marginBottom: "20px" }}>
              <div style={{ background: "#fff", border: "1px solid #cbd5e1", borderRadius: "8px", padding: "16px" }}>
                <div style={{ fontSize: "14px", color: "#64748b" }}>{t.metrics.totalBilled}</div>
                <div style={{ fontSize: "24px", fontWeight: "bold", color: "#0f172a", marginTop: "8px" }}>
                  ₹4,50,000.00
                </div>
              </div>
              <div style={{ background: "#fff", border: "1px solid #cbd5e1", borderRadius: "8px", padding: "16px" }}>
                <div style={{ fontSize: "14px", color: "#64748b" }}>{t.metrics.totalCollected}</div>
                <div style={{ fontSize: "24px", fontWeight: "bold", color: "#16a34a", marginTop: "8px" }}>
                  ₹3,85,000.00
                </div>
              </div>
              <div style={{ background: "#fff", border: "1px solid #cbd5e1", borderRadius: "8px", padding: "16px" }}>
                <div style={{ fontSize: "14px", color: "#64748b" }}>{t.metrics.outstandingDues}</div>
                <div style={{ fontSize: "24px", fontWeight: "bold", color: "#dc2626", marginTop: "8px" }}>
                  ₹65,000.00
                </div>
              </div>
              <div style={{ background: "#fff", border: "1px solid #cbd5e1", borderRadius: "8px", padding: "16px" }}>
                <div style={{ fontSize: "14px", color: "#64748b" }}>{t.metrics.collectionRate}</div>
                <div style={{ fontSize: "24px", fontWeight: "bold", color: "#2563eb", marginTop: "8px" }}>
                  85.5%
                </div>
              </div>
            </div>
          )}

          {/* Invoices List Tab */}
          {activeTab === "invoices" && (
            <div style={{ background: "#fff", border: "1px solid #cbd5e1", borderRadius: "8px", padding: "20px" }}>
              <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "16px" }}>
                <h3 style={{ margin: 0 }}>Maintenance Invoices & Balances</h3>
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
                    {t.buttons.generateInvoices}
                  </button>
                )}
              </div>
              <table style={{ width: "100%", borderCollapse: "collapse", textAlign: "left" }}>
                <thead>
                  <tr style={{ background: "#f1f5f9" }}>
                    <th style={{ padding: "10px", borderBottom: "1px solid #cbd5e1" }}>{t.table.invoiceNo}</th>
                    <th style={{ padding: "10px", borderBottom: "1px solid #cbd5e1" }}>{t.table.unit}</th>
                    <th style={{ padding: "10px", borderBottom: "1px solid #cbd5e1" }}>{t.table.amount}</th>
                    <th style={{ padding: "10px", borderBottom: "1px solid #cbd5e1" }}>{t.table.dueDate}</th>
                    <th style={{ padding: "10px", borderBottom: "1px solid #cbd5e1" }}>{t.table.status}</th>
                  </tr>
                </thead>
                <tbody>
                  {invoices.map((inv) => (
                    <tr key={inv.invoiceNo}>
                      <td style={{ padding: "10px", borderBottom: "1px solid #e2e8f0" }}>{inv.invoiceNo}</td>
                      <td style={{ padding: "10px", borderBottom: "1px solid #e2e8f0" }}>{inv.unit}</td>
                      <td style={{ padding: "10px", borderBottom: "1px solid #e2e8f0", fontWeight: "bold" }}>
                        ₹{inv.amount.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                      </td>
                      <td style={{ padding: "10px", borderBottom: "1px solid #e2e8f0" }}>{inv.dueDate}</td>
                      <td style={{ padding: "10px", borderBottom: "1px solid #e2e8f0" }}>
                        <span
                          style={{
                            padding: "4px 8px",
                            borderRadius: "4px",
                            fontSize: "12px",
                            fontWeight: "bold",
                            background: inv.status === "PAID" ? "#dcfce7" : "#fee2e2",
                            color: inv.status === "PAID" ? "#15803d" : "#b91c1c",
                          }}
                        >
                          {inv.status}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* Rules Tab (Admin Only) */}
          {activeTab === "rules" && mode === "ADMIN" && (
            <div style={{ background: "#fff", border: "1px solid #cbd5e1", borderRadius: "8px", padding: "20px" }}>
              <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "16px" }}>
                <h3 style={{ margin: 0 }}>Active Charge Calculation Rules</h3>
                <button style={{ padding: "8px 16px", background: "#2563eb", color: "#fff", border: "none", borderRadius: "6px" }}>
                  {t.buttons.newRule}
                </button>
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
                <div style={{ border: "1px solid #e2e8f0", borderRadius: "6px", padding: "16px", background: "#f8fafc" }}>
                  <strong>Flat Rate Operating Charge</strong>
                  <div style={{ fontSize: "14px", color: "#64748b", marginTop: "4px" }}>
                    Flat ₹2,500 per month per unit for common area maintenance.
                  </div>
                </div>
                <div style={{ border: "1px solid #e2e8f0", borderRadius: "6px", padding: "16px", background: "#f8fafc" }}>
                  <strong>Area-Based Sinking Fund Rule</strong>
                  <div style={{ fontSize: "14px", color: "#64748b", marginTop: "4px" }}>
                    ₹1.50 per sq ft super built-up area for capital reserve fund.
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
