"use client";

import React, { useState } from "react";

// Internationalization Dictionaries (English & Tamil)
const i18n = {
  en: {
    title: "Committee, Meetings & Governance",
    subtitle: "Manage managing committee, general body meetings, formal resolutions, voting, and meeting minutes.",
    easyMode: "Easy Mode",
    standardMode: "Standard Mode",
    adminMode: "Admin Mode",
    language: "Language",
    english: "English",
    tamil: "தமிழ்",
    tabs: {
      committees: "Committees",
      meetings: "Meetings",
      resolutions: "Resolutions & Voting",
      minutes: "Meeting Minutes",
      actionItems: "Action Items",
    },
    status: {
      draft: "Draft",
      scheduled: "Scheduled",
      inProgress: "In Progress",
      completed: "Completed",
      adjourned: "Adjourned",
      cancelled: "Cancelled",
      proposed: "Proposed",
      underReview: "Under Review",
      votingOpen: "Voting Open",
      passed: "Passed",
      rejected: "Rejected",
      withdrawn: "Withdrawn",
      pending: "Pending",
      approved: "Approved",
      published: "Published",
    },
    buttons: {
      createCommittee: "+ Create Committee",
      createMeeting: "+ Schedule Meeting",
      proposeResolution: "+ Propose Resolution",
      recordQuorum: "Calculate Quorum",
      castVote: "Cast Vote",
      voteFor: "FOR (YES)",
      voteAgainst: "AGAINST (NO)",
      voteAbstain: "ABSTAIN",
      prepareMinutes: "+ Draft Minutes",
      approveMinutes: "Approve & Publish Minutes",
      createActionItem: "+ Add Action Item",
      viewDetails: "View Details",
    },
    quorumStatus: {
      achieved: "Quorum Achieved ✅",
      notAchieved: "Quorum Not Achieved ❌",
    },
    sampleData: {
      agmTitle: "🏛️ 15th Annual General Body Meeting (AGM 2026)",
      agmDesc: "Annual review of financial accounts, appointment of auditor, and major facility renovation proposals.",
      mcTitle: "📋 Managing Committee Monthly Review",
      mcDesc: "Monthly operational review of maintenance complaints, vendor performance, and budget variance.",
      res1Title: "RES-2026-000001: Solar Rooftop Installation Project",
      res1Desc: "Approval of ₹15,000,000 capital expenditure for 100kW rooftop solar grid system across Blocks A-D.",
      res2Title: "RES-2026-000002: Visitor Parking Fee Policy Revision",
      res2Desc: "Proposal to modify visitor parking rate card and overnight parking limits.",
      minutesTitle: "Minutes of 14th AGM (Published)",
      minutesDesc: "Approved minutes of the previous AGM held on October 15, 2025.",
    },
  },
  ta: {
    title: "குழுக்கள், கூட்டங்கள் & நிர்வாகம்",
    subtitle: "நிர்வாகக் குழு, பொதுக்குழு கூட்டங்கள், தீர்மானங்கள், வாக்களிப்பு மற்றும் கூட்ட முடிவுகளை நிர்வகிக்கவும்.",
    easyMode: "எளிய முறை",
    standardMode: "நிலையான முறை",
    adminMode: "நிர்வாகி முறை",
    language: "மொழி",
    english: "English",
    tamil: "தமிழ்",
    tabs: {
      committees: "குழுக்கள்",
      meetings: "கூட்டங்கள்",
      resolutions: "தீர்மானங்கள் & வாக்குப்பதிவு",
      minutes: "கூட்ட முடிவுகள் (Minutes)",
      actionItems: "செயல்பாடுகள்",
    },
    status: {
      draft: "வரைவு",
      scheduled: "திட்டமிடப்பட்டது",
      inProgress: "நடைபெறுகிறது",
      completed: "முடிவுற்றது",
      adjourned: "ஒத்திவைக்கப்பட்டது",
      cancelled: "ரத்து செய்யப்பட்டது",
      proposed: "முன்மொழியப்பட்டது",
      underReview: "பரிசீலனையில்",
      votingOpen: "வாக்குப்பதிவு நடப்பில்",
      passed: "நிறைவேற்றப்பட்டது",
      rejected: "நிராகரிக்கப்பட்டது",
      withdrawn: "திரும்பப் பெறப்பட்டது",
      pending: "நிலுவையில்",
      approved: "ஒப்புதல் அளிக்கப்பட்டது",
      published: "வெளியிடப்பட்டது",
    },
    buttons: {
      createCommittee: "+ புதிய குழு",
      createMeeting: "+ கூட்டம் திட்டமிடு",
      proposeResolution: "+ தீர்மானம் முன்மொழி",
      recordQuorum: "குவோரம் கணக்கிடு",
      castVote: "வாக்களிக்கவும்",
      voteFor: "ஆதரவு (ஆம்)",
      voteAgainst: "எதிர்ப்பு (இல்லை)",
      voteAbstain: "நடுநிலை",
      prepareMinutes: "+ வரைவு முடிவுகள்",
      approveMinutes: "முடிவுகளை ஒப்புதல் அளித்து வெளியிடு",
      createActionItem: "+ புதிய நடவடிக்கை",
      viewDetails: "விவரங்களைப் பார்க்க",
    },
    quorumStatus: {
      achieved: "குவோரம் எட்டப்பட்டது ✅",
      notAchieved: "குவோரம் எட்டப்படவில்லை ❌",
    },
    sampleData: {
      agmTitle: "🏛️ 15-வது வருடாந்திர பொதுக்குழு கூட்டம் (AGM 2026)",
      agmDesc: "ஆண்டு நிதி தணிக்கை அறிக்கை, தணிக்கையாளர் நியமனம் மற்றும் வளாக புதுப்பித்தல் திட்டங்கள்.",
      mcTitle: "📋 நிர்வாகக் குழு மாதாந்திர ஆய்வுக் கூட்டம்",
      mcDesc: "பராமரிப்பு புகார்கள், சேவை வழங்குநர் செயல்பாடு மற்றும் வரவு-செலவு ஆய்வு.",
      res1Title: "RES-2026-000001: சோலார் கூரை மின் உற்பத்தி திட்டம்",
      res1Desc: "பிளாக் A-D கட்டிடங்களில் 100kW சோலார் மின்கலன்கள் நிறுவ ₹15,00,000 ஒதுக்கீட்டிற்கு ஒப்புதல்.",
      res2Title: "RES-2026-000002: பார்வையாளர்கள் வாகன நிறுத்துமிடக் கட்டண மாற்றம்",
      res2Desc: "பார்வையாளர் வாகனக் கட்டணம் மற்றும் இரவு நேர வாகன எல்லை விதியை திருத்துதல்.",
      minutesTitle: "14-வது AGM கூட்ட முடிவுகள் (வெளியிடப்பட்டது)",
      minutesDesc: "அக்டோபர் 15, 2025 அன்று நடைபெற்ற பொதுக்குழு கூட்டத்தின் ஒப்புதல் பெறப்பட்ட முடிவுகள்.",
    },
  },
};

type ViewMode = "easy" | "standard" | "admin";
type Lang = "en" | "ta";
type Tab = "committees" | "meetings" | "resolutions" | "minutes" | "actionItems";

export default function GovernancePage() {
  const [mode, setMode] = useState<ViewMode>("standard");
  const [lang, setLang] = useState<Lang>("en");
  const [activeTab, setActiveTab] = useState<Tab>("meetings");
  const [selectedVote, setSelectedVote] = useState<Record<string, string>>({});
  const [votedStatus, setVotedStatus] = useState<Record<string, boolean>>({});

  const t = i18n[lang];

  const handleVote = (resolutionId: string, choice: string) => {
    setSelectedVote((prev) => ({ ...prev, [resolutionId]: choice }));
    setVotedStatus((prev) => ({ ...prev, [resolutionId]: true }));
  };

  return (
    <div style={{ padding: "24px", maxWidth: "1200px", margin: "0 auto", fontFamily: "system-ui, sans-serif" }}>
      {/* Header Controls */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "20px" }}>
        <div>
          <h1 style={{ fontSize: "28px", fontWeight: "bold", margin: "0 0 8px 0" }}>{t.title}</h1>
          <p style={{ color: "#666", margin: 0 }}>{t.subtitle}</p>
        </div>
        <div style={{ display: "flex", gap: "12px", alignItems: "center" }}>
          {/* Mode Selector */}
          <div style={{ background: "#eee", padding: "4px", borderRadius: "8px", display: "flex", gap: "4px" }}>
            <button
              onClick={() => setMode("easy")}
              style={{
                padding: "6px 12px",
                border: "none",
                borderRadius: "6px",
                cursor: "pointer",
                background: mode === "easy" ? "#2563eb" : "transparent",
                color: mode === "easy" ? "#fff" : "#333",
                fontWeight: mode === "easy" ? "bold" : "normal",
              }}
            >
              {t.easyMode}
            </button>
            <button
              onClick={() => setMode("standard")}
              style={{
                padding: "6px 12px",
                border: "none",
                borderRadius: "6px",
                cursor: "pointer",
                background: mode === "standard" ? "#2563eb" : "transparent",
                color: mode === "standard" ? "#fff" : "#333",
                fontWeight: mode === "standard" ? "bold" : "normal",
              }}
            >
              {t.standardMode}
            </button>
            <button
              onClick={() => setMode("admin")}
              style={{
                padding: "6px 12px",
                border: "none",
                borderRadius: "6px",
                cursor: "pointer",
                background: mode === "admin" ? "#2563eb" : "transparent",
                color: mode === "admin" ? "#fff" : "#333",
                fontWeight: mode === "admin" ? "bold" : "normal",
              }}
            >
              {t.adminMode}
            </button>
          </div>
          {/* Language Selector */}
          <button
            onClick={() => setLang(lang === "en" ? "ta" : "en")}
            style={{
              padding: "6px 16px",
              border: "1px solid #ccc",
              borderRadius: "6px",
              background: "#fff",
              cursor: "pointer",
              fontWeight: "500",
            }}
          >
            🌐 {lang === "en" ? t.tamil : t.english}
          </button>
        </div>
      </div>

      {/* EASY MODE VIEW */}
      {mode === "easy" && (
        <div style={{ display: "flex", flexDirection: "column", gap: "20px" }}>
          {/* Active Voting Section */}
          <div style={{ border: "1px solid #e5e7eb", borderRadius: "12px", padding: "20px", background: "#f9fafb" }}>
            <h2 style={{ fontSize: "20px", marginTop: 0 }}>🗳️ Active Resolution Voting</h2>
            <div style={{ border: "1px solid #d1d5db", borderRadius: "8px", padding: "16px", background: "#fff", marginBottom: "16px" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
                <div>
                  <h3 style={{ margin: "0 0 8px 0", color: "#1d4ed8" }}>{t.sampleData.res1Title}</h3>
                  <p style={{ color: "#4b5563", margin: "0 0 12px 0" }}>{t.sampleData.res1Desc}</p>
                  <span style={{ background: "#dbeafe", color: "#1e40af", padding: "4px 8px", borderRadius: "4px", fontSize: "12px", fontWeight: "bold" }}>
                    {t.status.votingOpen} • Majority: 2/3 (66.7%)
                  </span>
                </div>
              </div>
              <div style={{ marginTop: "16px", display: "flex", gap: "12px" }}>
                {!votedStatus["res1"] ? (
                  <>
                    <button
                      onClick={() => handleVote("res1", "FOR")}
                      style={{ padding: "10px 20px", background: "#16a34a", color: "#fff", border: "none", borderRadius: "6px", fontWeight: "bold", cursor: "pointer" }}
                    >
                      {t.buttons.voteFor}
                    </button>
                    <button
                      onClick={() => handleVote("res1", "AGAINST")}
                      style={{ padding: "10px 20px", background: "#dc2626", color: "#fff", border: "none", borderRadius: "6px", fontWeight: "bold", cursor: "pointer" }}
                    >
                      {t.buttons.voteAgainst}
                    </button>
                    <button
                      onClick={() => handleVote("res1", "ABSTAIN")}
                      style={{ padding: "10px 20px", background: "#4b5563", color: "#fff", border: "none", borderRadius: "6px", fontWeight: "bold", cursor: "pointer" }}
                    >
                      {t.buttons.voteAbstain}
                    </button>
                  </>
                ) : (
                  <div style={{ padding: "10px 16px", background: "#f0fdf4", color: "#15803d", borderRadius: "6px", fontWeight: "bold" }}>
                    ✅ Vote Cast: {selectedVote["res1"]}
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* Upcoming Meetings */}
          <div style={{ border: "1px solid #e5e7eb", borderRadius: "12px", padding: "20px", background: "#fff" }}>
            <h2 style={{ fontSize: "20px", marginTop: 0 }}>📅 Upcoming Meetings</h2>
            <div style={{ border: "1px solid #e5e7eb", borderRadius: "8px", padding: "16px" }}>
              <h3 style={{ margin: "0 0 8px 0" }}>{t.sampleData.agmTitle}</h3>
              <p style={{ color: "#6b7280", margin: "0 0 8px 0" }}>{t.sampleData.agmDesc}</p>
              <div style={{ fontSize: "14px", color: "#374151" }}>
                📆 <strong>Date:</strong> October 25, 2026 | ⏰ <strong>Time:</strong> 10:00 AM | 📍 <strong>Venue:</strong> Society Clubhouse Main Hall
              </div>
            </div>
          </div>
        </div>
      )}

      {/* STANDARD AND ADMIN MODES VIEW */}
      {mode !== "easy" && (
        <div>
          {/* Navigation Tabs */}
          <div style={{ display: "flex", gap: "8px", borderBottom: "2px solid #e5e7eb", marginBottom: "20px" }}>
            {(["committees", "meetings", "resolutions", "minutes", "actionItems"] as Tab[]).map((tab) => (
              <button
                key={tab}
                onClick={() => setActiveTab(tab)}
                style={{
                  padding: "10px 16px",
                  border: "none",
                  borderBottom: activeTab === tab ? "3px solid #2563eb" : "3px solid transparent",
                  background: "transparent",
                  color: activeTab === tab ? "#2563eb" : "#4b5563",
                  fontWeight: activeTab === tab ? "bold" : "normal",
                  cursor: "pointer",
                }}
              >
                {t.tabs[tab]}
              </button>
            ))}
          </div>

          {/* Admin Action Bar */}
          {mode === "admin" && (
            <div style={{ background: "#eff6ff", border: "1px solid #bfdbfe", padding: "12px 16px", borderRadius: "8px", marginBottom: "20px", display: "flex", gap: "12px" }}>
              {activeTab === "committees" && <button style={{ background: "#2563eb", color: "#fff", border: "none", padding: "8px 16px", borderRadius: "6px", fontWeight: "bold", cursor: "pointer" }}>{t.buttons.createCommittee}</button>}
              {activeTab === "meetings" && (
                <>
                  <button style={{ background: "#2563eb", color: "#fff", border: "none", padding: "8px 16px", borderRadius: "6px", fontWeight: "bold", cursor: "pointer" }}>{t.buttons.createMeeting}</button>
                  <button style={{ background: "#16a34a", color: "#fff", border: "none", padding: "8px 16px", borderRadius: "6px", fontWeight: "bold", cursor: "pointer" }}>{t.buttons.recordQuorum}</button>
                </>
              )}
              {activeTab === "resolutions" && <button style={{ background: "#2563eb", color: "#fff", border: "none", padding: "8px 16px", borderRadius: "6px", fontWeight: "bold", cursor: "pointer" }}>{t.buttons.proposeResolution}</button>}
              {activeTab === "minutes" && (
                <>
                  <button style={{ background: "#2563eb", color: "#fff", border: "none", padding: "8px 16px", borderRadius: "6px", fontWeight: "bold", cursor: "pointer" }}>{t.buttons.prepareMinutes}</button>
                  <button style={{ background: "#059669", color: "#fff", border: "none", padding: "8px 16px", borderRadius: "6px", fontWeight: "bold", cursor: "pointer" }}>{t.buttons.approveMinutes}</button>
                </>
              )}
              {activeTab === "actionItems" && <button style={{ background: "#2563eb", color: "#fff", border: "none", padding: "8px 16px", borderRadius: "6px", fontWeight: "bold", cursor: "pointer" }}>{t.buttons.createActionItem}</button>}
            </div>
          )}

          {/* TAB CONTENT */}
          {activeTab === "meetings" && (
            <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
              <div style={{ border: "1px solid #e5e7eb", borderRadius: "8px", padding: "16px", background: "#fff" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <span style={{ fontSize: "12px", fontWeight: "bold", background: "#e0e7ff", color: "#3730a3", padding: "2px 8px", borderRadius: "4px" }}>
                    MTG-2026-000001
                  </span>
                  <span style={{ background: "#dcfce7", color: "#15803d", padding: "2px 8px", borderRadius: "4px", fontSize: "12px", fontWeight: "bold" }}>
                    {t.status.scheduled} • {t.quorumStatus.achieved}
                  </span>
                </div>
                <h3 style={{ margin: "8px 0" }}>{t.sampleData.agmTitle}</h3>
                <p style={{ color: "#6b7280", margin: "0 0 12px 0" }}>{t.sampleData.agmDesc}</p>
                <div style={{ display: "flex", gap: "24px", fontSize: "14px", color: "#374151" }}>
                  <span>📅 Oct 25, 2026</span>
                  <span>⏰ 10:00 AM</span>
                  <span>📍 Clubhouse Main Hall</span>
                  <span>👥 Target Quorum: 50%</span>
                </div>
              </div>
            </div>
          )}

          {activeTab === "resolutions" && (
            <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
              <div style={{ border: "1px solid #e5e7eb", borderRadius: "8px", padding: "16px", background: "#fff" }}>
                <div style={{ display: "flex", justifyContent: "space-between" }}>
                  <h3 style={{ margin: "0 0 8px 0" }}>{t.sampleData.res1Title}</h3>
                  <span style={{ background: "#fef3c7", color: "#92400e", padding: "2px 8px", borderRadius: "4px", fontSize: "12px", fontWeight: "bold" }}>
                    {t.status.votingOpen}
                  </span>
                </div>
                <p style={{ color: "#4b5563" }}>{t.sampleData.res1Desc}</p>
                <div style={{ display: "flex", gap: "16px", marginTop: "12px", fontSize: "14px" }}>
                  <span>👍 FOR: 45</span>
                  <span>👎 AGAINST: 5</span>
                  <span>✋ ABSTAIN: 2</span>
                  <span>📊 Total Votes: 52 / 80 Eligible</span>
                </div>
              </div>
            </div>
          )}

          {activeTab === "committees" && (
            <div style={{ border: "1px solid #e5e7eb", borderRadius: "8px", padding: "16px", background: "#fff" }}>
              <h3 style={{ margin: "0 0 8px 0" }}>Executive Managing Committee (MC)</h3>
              <p style={{ color: "#6b7280" }}>Primary elected governing body of the society responsible for administration, finance, and operations.</p>
              <div style={{ marginTop: "12px", fontSize: "14px" }}>
                <strong>Members (7):</strong> President, Vice President, Secretary, Joint Secretary, Treasurer, 2 Executive Members
              </div>
            </div>
          )}

          {activeTab === "minutes" && (
            <div style={{ border: "1px solid #e5e7eb", borderRadius: "8px", padding: "16px", background: "#fff" }}>
              <div style={{ display: "flex", justifyContent: "space-between" }}>
                <h3 style={{ margin: "0 0 8px 0" }}>{t.sampleData.minutesTitle}</h3>
                <span style={{ background: "#d1fae5", color: "#065f46", padding: "2px 8px", borderRadius: "4px", fontSize: "12px", fontWeight: "bold" }}>
                  {t.status.published} (Version 1)
                </span>
              </div>
              <p style={{ color: "#6b7280" }}>{t.sampleData.minutesDesc}</p>
              <button style={{ marginTop: "8px", padding: "6px 12px", background: "#f3f4f6", border: "1px solid #d1d5db", borderRadius: "4px", cursor: "pointer" }}>
                📄 Download Minutes PDF
              </button>
            </div>
          )}

          {activeTab === "actionItems" && (
            <div style={{ border: "1px solid #e5e7eb", borderRadius: "8px", padding: "16px", background: "#fff" }}>
              <h3 style={{ margin: "0 0 8px 0" }}>ACT-2026-001: Obtain Solar Vendor Quotations</h3>
              <p style={{ color: "#6b7280" }}>Procure 3 competitive vendor quotations for 100kW solar installation by Nov 15, 2026.</p>
              <div style={{ display: "flex", gap: "16px", fontSize: "14px" }}>
                <span>👤 Assignee: Joint Secretary</span>
                <span>📌 Status: In Progress</span>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
