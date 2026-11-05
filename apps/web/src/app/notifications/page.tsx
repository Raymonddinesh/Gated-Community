"use client";

import React, { useState, useEffect } from "react";
import { apiClient } from "@/lib/api-client";

// Internationalization Dictionaries (English & Tamil)
const i18n = {
  en: {
    title: "Notifications & Communication Inbox",
    subtitle: "Centralized multi-channel communication inbox, template manager, and preference center.",
    easyMode: "Easy Mode",
    standardMode: "Standard Mode",
    adminMode: "Admin Mode",
    language: "Language",
    english: "English",
    tamil: "தமிழ்",
    unreadBadge: "Unread Notifications",
    tabs: {
      inbox: "Inbox",
      preferences: "Notification Preferences",
      templates: "Templates Catalog",
      deliveries: "Delivery Logs",
      providers: "Communication Providers",
    },
    easyView: {
      heading: "Simple Inbox",
      markAllRead: "Mark All as Read",
      noNotifications: "You have no new notifications.",
    },
    categories: {
      emergency: "Emergency 🚨",
      announcement: "Announcement 📢",
      billing: "Billing 💳",
      governance: "Governance 🏛️",
      complaint: "Complaint 🛠️",
      event: "Event 🎉",
      facility: "Facility 🏢",
      maintenance: "Maintenance 🔧",
      general: "General ℹ️",
    },
    channels: {
      inApp: "In-App Inbox",
      email: "Email",
      sms: "SMS",
      whatsapp: "WhatsApp",
      push: "Push Notification",
    },
    buttons: {
      sendBroadcast: "+ Send Broadcast",
      createTemplate: "+ Create Template",
      markRead: "Mark Read",
      savePreferences: "Save Preferences",
      registerDevice: "Register Mobile Device",
    },
  },
  ta: {
    title: "அறிவிப்புகள் மற்றும் தொடர்பு உறை",
    subtitle: "மையப்படுத்தப்பட்ட பல சேனல் அறிவிப்புகள் உறை மற்றும் அமைப்புகள் மையம்.",
    easyMode: "எளிதான பயன்முறை",
    standardMode: "சாதாரண பயன்முறை",
    adminMode: "நிர்வாகி பயன்முறை",
    language: "மொழி",
    english: "English",
    tamil: "தமிழ்",
    unreadBadge: "படிக்காத அறிவிப்புகள்",
    tabs: {
      inbox: "அறிவிப்புகள் உறை",
      preferences: "விருப்பத்தேர்வுகள்",
      templates: "வார்ப்புருக்கள்",
      deliveries: "டெலிவரி பதிவுகள்",
      providers: "தொடர்பு சேவைகள்",
    },
    easyView: {
      heading: "எளிய அறிவிப்புகள்",
      markAllRead: "அனைத்தையும் படித்ததாக குறிக்க",
      noNotifications: "புதிய அறிவிப்புகள் எதுவும் இல்லை.",
    },
    categories: {
      emergency: "அவசரம் 🚨",
      announcement: "அறிவிப்பு 📢",
      billing: "கட்டணம் 💳",
      governance: "நிர்வாகம் 🏛️",
      complaint: "புகார் 🛠️",
      event: "நிகழ்ச்சி 🎉",
      facility: "வசதி 🏢",
      maintenance: "பராமரிப்பு 🔧",
      general: "பொதுவானது ℹ️",
    },
    channels: {
      inApp: "செயலி உறை",
      email: "மின்னஞ்சல்",
      sms: "குறுஞ்செய்தி (SMS)",
      whatsapp: "வாட்ஸ்அப்",
      push: "புஷ் அறிவிப்பு",
    },
    buttons: {
      sendBroadcast: "+ பொது அறிவிப்பு அனுப்புக",
      createTemplate: "+ புதிய வார்ப்புரு உருவாக்க",
      markRead: "படித்ததாக குறிக்கவும்",
      savePreferences: "சேமிக்கவும்",
      registerDevice: "சாதனம் பதிவு செய்ய",
    },
  },
};

// Sample Initial Mock Inbox Items for UI Rendering
const initialNotifications = [
  {
    id: "n-101",
    title: "🚨 EMERGENCY: Fire Alarm Triggered in Block A",
    content: "Fire alarm activated on Floor 4, Block A. Please evacuate via emergency stairwells immediately.",
    category: "EMERGENCY",
    priority: "CRITICAL",
    isRead: false,
    createdAt: "2026-10-06 14:00",
    channel: "IN_APP",
  },
  {
    id: "n-102",
    title: "Annual General Body Meeting Scheduled",
    content: "The AGM is scheduled for October 25th at 10:00 AM in the Main Clubhouse Auditorium.",
    category: "GOVERNANCE",
    priority: "NORMAL",
    isRead: false,
    createdAt: "2026-10-06 11:30",
    channel: "IN_APP",
  },
  {
    id: "n-103",
    title: "Maintenance Bill Issued for October 2026",
    content: "Your monthly maintenance invoice #INV-202610-004 for ₹3,500 has been generated. Due Date: Oct 15.",
    category: "BILLING",
    priority: "NORMAL",
    isRead: true,
    createdAt: "2026-10-05 09:00",
    channel: "IN_APP",
  },
];

export default function NotificationsPage() {
  const [lang, setLang] = useState<"en" | "ta">("en");
  const [mode, setMode] = useState<"EASY" | "STANDARD" | "ADMIN">("STANDARD");
  const [activeTab, setActiveTab] = useState<"inbox" | "preferences" | "templates" | "deliveries" | "providers">("inbox");
  const [notifications, setNotifications] = useState(initialNotifications);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function fetchInbox() {
      try {
        setLoading(true);
        const data = await apiClient<Array<{
          id: string;
          title: string;
          content: string;
          category: string;
          priority: string;
          is_read: boolean;
          created_at: string;
        }>>('/api/v1/notifications/inbox');

        if (data && Array.isArray(data)) {
          setNotifications(data.map(item => ({
            id: item.id,
            title: item.title,
            content: item.content,
            category: item.category,
            priority: item.priority,
            isRead: item.is_read,
            createdAt: item.created_at,
            channel: 'IN_APP',
          })));
        }
      } catch (err: unknown) {
        // Fallback to initial mock view on connection error or unauthenticated state
        setError(err instanceof Error ? err.message : 'API connection failed');
      } finally {
        setLoading(false);
      }
    }
    fetchInbox();
  }, []);

  const t = i18n[lang];

  const markRead = (id: string) => {
    setNotifications((prev) =>
      prev.map((n) => (n.id === id ? { ...n, isRead: true } : n))
    );
  };

  const markAllRead = () => {
    setNotifications((prev) => prev.map((n) => ({ ...n, isRead: true })));
  };

  const unreadCount = notifications.filter((n) => !n.isRead).length;

  return (
    <div style={{ padding: "24px", maxWidth: "1200px", margin: "0 auto", fontFamily: "system-ui, sans-serif" }}>
      {/* Header Controls */}
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
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "20px" }}>
            <h2 style={{ fontSize: "24px", margin: 0 }}>
              {t.easyView.heading} ({unreadCount} {t.unreadBadge})
            </h2>
            <button
              onClick={markAllRead}
              style={{
                padding: "12px 24px",
                fontSize: "18px",
                fontWeight: "bold",
                background: "#16a34a",
                color: "#fff",
                border: "none",
                borderRadius: "8px",
                cursor: "pointer",
              }}
            >
              {t.easyView.markAllRead}
            </button>
          </div>

          {notifications.length === 0 ? (
            <p style={{ fontSize: "18px", color: "#64748b" }}>{t.easyView.noNotifications}</p>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
              {notifications.map((item) => (
                <div
                  key={item.id}
                  style={{
                    background: item.isRead ? "#ffffff" : "#fef2f2",
                    borderLeft: item.priority === "CRITICAL" ? "8px solid #dc2626" : "6px solid #2563eb",
                    borderRadius: "8px",
                    padding: "20px",
                    boxShadow: "0 2px 4px rgba(0,0,0,0.05)",
                  }}
                >
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
                    <div>
                      <h3 style={{ fontSize: "20px", margin: "0 0 8px 0" }}>{item.title}</h3>
                      <p style={{ fontSize: "16px", color: "#334155", margin: 0 }}>{item.content}</p>
                      <span style={{ fontSize: "14px", color: "#94a3b8", display: "block", marginTop: "8px" }}>
                        {item.createdAt}
                      </span>
                    </div>
                    {!item.isRead && (
                      <button
                        onClick={() => markRead(item.id)}
                        style={{
                          padding: "10px 18px",
                          fontSize: "16px",
                          background: "#2563eb",
                          color: "#fff",
                          border: "none",
                          borderRadius: "6px",
                          cursor: "pointer",
                        }}
                      >
                        {t.buttons.markRead}
                      </button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* STANDARD & ADMIN MODES UI */}
      {mode !== "EASY" && (
        <div>
          {/* Navigation Tabs */}
          <div style={{ display: "flex", gap: "8px", borderBottom: "2px solid #e2e8f0", marginBottom: "20px" }}>
            <button
              onClick={() => setActiveTab("inbox")}
              style={{
                padding: "12px 20px",
                border: "none",
                borderBottom: activeTab === "inbox" ? "3px solid #2563eb" : "none",
                background: "transparent",
                fontWeight: activeTab === "inbox" ? "bold" : "normal",
                cursor: "pointer",
              }}
            >
              {t.tabs.inbox} ({unreadCount})
            </button>
            <button
              onClick={() => setActiveTab("preferences")}
              style={{
                padding: "12px 20px",
                border: "none",
                borderBottom: activeTab === "preferences" ? "3px solid #2563eb" : "none",
                background: "transparent",
                fontWeight: activeTab === "preferences" ? "bold" : "normal",
                cursor: "pointer",
              }}
            >
              {t.tabs.preferences}
            </button>
            {mode === "ADMIN" && (
              <>
                <button
                  onClick={() => setActiveTab("templates")}
                  style={{
                    padding: "12px 20px",
                    border: "none",
                    borderBottom: activeTab === "templates" ? "3px solid #2563eb" : "none",
                    background: "transparent",
                    fontWeight: activeTab === "templates" ? "bold" : "normal",
                    cursor: "pointer",
                  }}
                >
                  {t.tabs.templates}
                </button>
                <button
                  onClick={() => setActiveTab("deliveries")}
                  style={{
                    padding: "12px 20px",
                    border: "none",
                    borderBottom: activeTab === "deliveries" ? "3px solid #2563eb" : "none",
                    background: "transparent",
                    fontWeight: activeTab === "deliveries" ? "bold" : "normal",
                    cursor: "pointer",
                  }}
                >
                  {t.tabs.deliveries}
                </button>
                <button
                  onClick={() => setActiveTab("providers")}
                  style={{
                    padding: "12px 20px",
                    border: "none",
                    borderBottom: activeTab === "providers" ? "3px solid #2563eb" : "none",
                    background: "transparent",
                    fontWeight: activeTab === "providers" ? "bold" : "normal",
                    cursor: "pointer",
                  }}
                >
                  {t.tabs.providers}
                </button>
              </>
            )}
          </div>

          {/* Inbox Tab */}
          {activeTab === "inbox" && (
            <div>
              <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "16px" }}>
                <span style={{ fontSize: "16px", fontWeight: "bold" }}>
                  Showing {notifications.length} notifications
                </span>
                <button
                  onClick={markAllRead}
                  style={{
                    padding: "8px 16px",
                    background: "#e2e8f0",
                    border: "none",
                    borderRadius: "6px",
                    cursor: "pointer",
                  }}
                >
                  {t.easyView.markAllRead}
                </button>
              </div>

              <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
                {notifications.map((item) => (
                  <div
                    key={item.id}
                    style={{
                      background: item.isRead ? "#fff" : "#eff6ff",
                      border: "1px solid #cbd5e1",
                      borderRadius: "8px",
                      padding: "16px",
                    }}
                  >
                    <div style={{ display: "flex", justifyContent: "space-between" }}>
                      <span
                        style={{
                          fontSize: "12px",
                          fontWeight: "bold",
                          padding: "2px 8px",
                          borderRadius: "4px",
                          background: item.priority === "CRITICAL" ? "#fca5a5" : "#bfdbfe",
                          color: item.priority === "CRITICAL" ? "#7f1d1d" : "#1e40af",
                        }}
                      >
                        {item.category} • {item.priority}
                      </span>
                      <span style={{ fontSize: "12px", color: "#64748b" }}>{item.createdAt}</span>
                    </div>
                    <h4 style={{ fontSize: "16px", margin: "8px 0 4px 0" }}>{item.title}</h4>
                    <p style={{ fontSize: "14px", color: "#334155", margin: 0 }}>{item.content}</p>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Preferences Tab */}
          {activeTab === "preferences" && (
            <div style={{ background: "#fff", padding: "20px", border: "1px solid #cbd5e1", borderRadius: "8px" }}>
              <h3 style={{ marginTop: 0 }}>User Channel & Quiet Hours Preferences</h3>
              <p style={{ color: "#64748b" }}>
                Configure notifications per category. Note: 🚨 Emergency Critical Alerts will ALWAYS bypass Quiet Hours and channel opt-outs.
              </p>
              <div style={{ display: "flex", flexDirection: "column", gap: "16px", marginTop: "20px" }}>
                {["EMERGENCY", "ANNOUNCEMENT", "BILLING", "GOVERNANCE", "COMPLAINT", "MAINTENANCE"].map((cat) => (
                  <div
                    key={cat}
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "center",
                      padding: "12px",
                      background: "#f8fafc",
                      borderRadius: "6px",
                    }}
                  >
                    <div>
                      <strong>{cat}</strong>
                      <div style={{ fontSize: "12px", color: "#64748b" }}>
                        Channels: In-App, Email, SMS, Push
                      </div>
                    </div>
                    <input type="checkbox" defaultChecked style={{ width: "20px", height: "20px" }} />
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Templates Tab (Admin Only) */}
          {activeTab === "templates" && mode === "ADMIN" && (
            <div style={{ background: "#fff", padding: "20px", border: "1px solid #cbd5e1", borderRadius: "8px" }}>
              <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "16px" }}>
                <h3 style={{ margin: 0 }}>System & Society Notification Templates</h3>
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
                  {t.buttons.createTemplate}
                </button>
              </div>
              <table style={{ width: "100%", borderCollapse: "collapse", textAlign: "left" }}>
                <thead>
                  <tr style={{ background: "#f1f5f9" }}>
                    <th style={{ padding: "10px", borderBottom: "1px solid #cbd5e1" }}>Code</th>
                    <th style={{ padding: "10px", borderBottom: "1px solid #cbd5e1" }}>Name</th>
                    <th style={{ padding: "10px", borderBottom: "1px solid #cbd5e1" }}>Category</th>
                    <th style={{ padding: "10px", borderBottom: "1px solid #cbd5e1" }}>Locales</th>
                    <th style={{ padding: "10px", borderBottom: "1px solid #cbd5e1" }}>Status</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td style={{ padding: "10px", borderBottom: "1px solid #e2e8f0" }}>EMERGENCY_ALERT_V1</td>
                    <td style={{ padding: "10px", borderBottom: "1px solid #e2e8f0" }}>Emergency Incident Broadcast</td>
                    <td style={{ padding: "10px", borderBottom: "1px solid #e2e8f0" }}>EMERGENCY</td>
                    <td style={{ padding: "10px", borderBottom: "1px solid #e2e8f0" }}>EN, TA</td>
                    <td style={{ padding: "10px", borderBottom: "1px solid #e2e8f0", color: "green" }}>ACTIVE</td>
                  </tr>
                  <tr>
                    <td style={{ padding: "10px", borderBottom: "1px solid #e2e8f0" }}>INVOICE_ISSUED_V1</td>
                    <td style={{ padding: "10px", borderBottom: "1px solid #e2e8f0" }}>Maintenance Bill Issued</td>
                    <td style={{ padding: "10px", borderBottom: "1px solid #e2e8f0" }}>BILLING</td>
                    <td style={{ padding: "10px", borderBottom: "1px solid #e2e8f0" }}>EN, TA</td>
                    <td style={{ padding: "10px", borderBottom: "1px solid #e2e8f0", color: "green" }}>ACTIVE</td>
                  </tr>
                </tbody>
              </table>
            </div>
          )}

          {/* Deliveries Tab (Admin Only) */}
          {activeTab === "deliveries" && mode === "ADMIN" && (
            <div style={{ background: "#fff", padding: "20px", border: "1px solid #cbd5e1", borderRadius: "8px" }}>
              <h3 style={{ marginTop: 0 }}>Channel Delivery Execution & Retry Logs</h3>
              <table style={{ width: "100%", borderCollapse: "collapse", textAlign: "left" }}>
                <thead>
                  <tr style={{ background: "#f1f5f9" }}>
                    <th style={{ padding: "10px" }}>Delivery ID</th>
                    <th style={{ padding: "10px" }}>Channel</th>
                    <th style={{ padding: "10px" }}>Status</th>
                    <th style={{ padding: "10px" }}>Attempts</th>
                    <th style={{ padding: "10px" }}>Timestamp</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td style={{ padding: "10px" }}>d-8801</td>
                    <td style={{ padding: "10px" }}>IN_APP</td>
                    <td style={{ padding: "10px", color: "green" }}>DELIVERED</td>
                    <td style={{ padding: "10px" }}>1/3</td>
                    <td style={{ padding: "10px" }}>2026-10-06 14:00</td>
                  </tr>
                </tbody>
              </table>
            </div>
          )}

          {/* Providers Tab (Admin Only) */}
          {activeTab === "providers" && mode === "ADMIN" && (
            <div style={{ background: "#fff", padding: "20px", border: "1px solid #cbd5e1", borderRadius: "8px" }}>
              <h3 style={{ marginTop: 0 }}>Communication Channel Adapters Status</h3>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: "16px" }}>
                {[
                  { channel: "IN_APP", name: "InAppProvider", status: "Active" },
                  { channel: "EMAIL", name: "MockEmailProvider", status: "Active (Provider Neutral)" },
                  { channel: "SMS", name: "MockSmsProvider", status: "Active (Provider Neutral)" },
                  { channel: "WHATSAPP", name: "MockWhatsAppProvider", status: "Active (Provider Neutral)" },
                  { channel: "PUSH", name: "MockPushProvider", status: "Active (Provider Neutral)" },
                ].map((p) => (
                  <div key={p.channel} style={{ border: "1px solid #cbd5e1", borderRadius: "6px", padding: "16px" }}>
                    <strong style={{ fontSize: "16px" }}>{p.channel}</strong>
                    <div style={{ color: "#64748b", marginTop: "4px" }}>{p.name}</div>
                    <span style={{ display: "inline-block", marginTop: "8px", color: "#16a34a", fontWeight: "bold" }}>
                      ● {p.status}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
