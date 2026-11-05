# ADR 002: Technology Stack & Modular Monolith Architecture

## Status
Accepted

## Context
SocietySphere requires a robust, strictly-typed, scalable backend and an accessible, responsive, high-performance web frontend. 
Future phases require developing a cross-platform mobile application in Flutter that reuses identical APIs and contracts. 
Microservices at this early stage introduce severe network latency, distributed transaction complexity (especially across double-entry financial ledgers), and operational overhead.

## Decision
1. **Backend**:
   - Runtime: Node.js (v20+ LTS) with TypeScript in strict mode.
   - Framework: **NestJS**. NestJS provides enterprise-grade dependency injection, built-in guards for multi-tenant isolation, validation pipes, interceptors for auditing, and first-class OpenAPI (Swagger) code generation.
   - ORM: **Prisma ORM** with PostgreSQL, providing type-safe queries, explicit schema migrations, and client extensions for tenant RLS injection.
   - Architecture Pattern: **Modular Monolith** with strict domain boundary isolation (`modules/billing`, `modules/gate-visitor`, `modules/identity`, etc.). Internal modules communicate via typed domain interfaces and NestJS event emitters, enabling easy future extraction into microservices if warranted.
2. **Frontend**:
   - Framework: **Next.js 14+ (App Router, TypeScript)** for the main portal and administration console.
   - Styling & UI Components: **Tailwind CSS** combined with **Radix UI (shadcn/ui)** for headless, fully accessible, keyboard-navigable components compliant with WCAG 2.1 AAA.
   - State & Data Fetching: **TanStack Query (React Query)** for declarative server-state management and caching; **Zustand** for lightweight client-side state.
3. **Mobile Client Parity**:
   - OpenAPI 3.0 specification auto-generated from backend controllers at `/api/v1/docs-json`.
   - Dart/Flutter SDK auto-generated using `openapi-generator-cli`, ensuring 100% type safety and zero drift between web and mobile interfaces.

## Consequences
### Positive
- Shared TypeScript types and paradigms across backend and web frontend.
- High developer velocity and compile-time safety.
- Modular monolith simplifies ACID transactions across society units, billings, and ledgers without distributed two-phase commits.
- Zero API contract drift with the future Flutter mobile application.

### Negative / Trade-offs
- Node.js single-threaded event loop requires offloading heavy CPU tasks (such as large PDF generation or bulk Excel exports) to asynchronous BullMQ worker processes.
