# ADR 005: Inclusive Design, "Easy Mode", Multilingual & Voice Foundation

## Status
Accepted

## Context
Apartment societies have a wide demographic spectrum. Many senior citizens, elderly residents, and security gate staff experience low digital literacy, visual impairments, or motor control challenges. 
Traditional SaaS platforms designed with dense, high-information-density UI tables and tiny typography alienate these users, leading to high failure rates for gate approvals, maintenance bill payments, and complaint filings.
Accessibility and multilingual capability cannot be retrofitted as an afterthought.

## Decision
1. **"Easy Mode" Persona & UX Framework**:
   - The frontend implements a persistent `Easy Mode` toggle accessible from the top navigation and onboarding.
   - Design Tokens in Easy Mode:
     - Base font size: 18px (up from 14px); headings 24px-32px.
     - Contrast ratios: strictly WCAG 2.1 AAA (> 7:1 contrast).
     - Interactive elements: minimum 48x48px hit areas.
     - Layout: Single-column linear flow with zero multi-level nested menus.
     - Iconography: Paired with clear, explicit textual labels (never icon-only buttons).
2. **Multilingual Architecture**:
   - `i18next` integrated at the foundational core with zero hardcoded English strings.
   - Phase 1 support: English, Hindi.
   - Architecture accommodates regional Indian languages (Kannada, Marathi, Tamil, Telugu, Bengali) via structured JSON translation namespaces.
3. **Voice UI Foundation**:
   - Integration of browser Web Speech API (SpeechRecognition & SpeechSynthesis).
   - Voice assistant input allows elderly users to dictate maintenance complaints ("My kitchen sink is leaking") or search society notices by voice.
   - Text-to-speech audio playback option for official society notices and emergency alerts.

## Consequences
### Positive
- High adoption among senior citizens and non-English-speaking residents.
- Significantly reduced training time for security guards and maintenance technicians.
- Full compliance with international accessibility standards (WCAG 2.1 AAA).

### Negative / Trade-offs
- Maintaining dual UI layouts (Standard Mode vs Easy Mode) requires disciplined component encapsulation in the design system.
