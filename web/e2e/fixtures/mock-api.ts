import { test as base, type Page } from "@playwright/test";
import {
  INCIDENT_ID,
  APPROVAL_ID,
  CONN_SSH_ID,
  createMockIncident,
  createMockIncidentList,
  createMockApprovalDecision,
  createMockConnection,
  createMockConnectionList,
  createMockServiceList,
} from "../helpers/mock-data";
import type { Connection, Service, SSEEvent } from "../../src/lib/types";
import {
  fulfillSSE,
  createAgentFlowEvents,
  createPostApprovalEvents,
  createResumeEvents,
} from "../helpers/sse-mock";

class MockApiHelper {
  /** Resolve function to unblock the SSE reconnection waiting for approval */
  private _approvedResolve: (() => void) | null = null;

  constructor(private page: Page) {}

  /** Set up all standard mocks (static SSE — for simple tests) */
  async setupAll() {
    await Promise.all([
      this.setupIncidentRoutes(),
      this.setupGetIncident(),
      this.setupSSEStream(),
      this.setupApproveDecide(),
      this.setupMessages(),
      this.setupSaveToMemory(),
    ]);
  }

  /**
   * Set up mocks with a two-phase SSE that simulates the real flow:
   *
   * 1. First SSE connection → sends pre-approval events, then closes
   * 2. EventSource auto-reconnects → handler waits for approval
   * 3. User approves → approval handler resolves the wait
   * 4. Second SSE connection → sends resume events (on the same page, no reload)
   */
  async setupAllLive() {
    await Promise.all([
      this.setupIncidentRoutes(),
      this.setupGetIncident(),
      this.setupLiveSSEStream(),
      this.setupApproveDecideLive(),
      this.setupMessages(),
      this.setupSaveToMemory(),
    ]);
  }

  /** GET /api/incidents → list, POST /api/incidents → create */
  async setupIncidentRoutes(incidents = createMockIncidentList()) {
    await this.page.route("**/api/incidents", async (route) => {
      const method = route.request().method();
      if (method === "GET") {
        await route.fulfill({ json: incidents });
      } else if (method === "POST") {
        await route.fulfill({ json: createMockIncident() });
      } else {
        await route.continue();
      }
    });
  }

  /** GET /api/incidents/:id → single incident */
  async setupGetIncident(incident = createMockIncident()) {
    await this.page.route(`**/api/incidents/${INCIDENT_ID}`, async (route) => {
      if (route.request().method() === "GET") {
        await route.fulfill({ json: incident });
      } else {
        await route.continue();
      }
    });
  }

  /** Static SSE: sends all events at once, then prevents reconnect replay */
  async setupSSEStream(events?: SSEEvent[]) {
    const sseEvents = events ?? createAgentFlowEvents();
    let fulfilled = false;

    await this.page.route(
      `**/api/incidents/${INCIDENT_ID}/stream`,
      async (route) => {
        if (!fulfilled) {
          fulfilled = true;
          await fulfillSSE(route, sseEvents);
        }
        // Subsequent reconnects: hang (never fulfill) to prevent duplicate events
      },
    );
  }

  /**
   * Live SSE using EventSource auto-reconnect:
   *
   * Connection 1: sends pre-approval events → closes
   * Connection 2: blocks until approval is given → sends resume events → closes
   * Connection 3+: hang (no more events)
   */
  async setupLiveSSEStream(
    preApprovalEvents?: SSEEvent[],
    resumeEvents?: SSEEvent[],
  ) {
    const pre = preApprovalEvents ?? createAgentFlowEvents();
    const resume = resumeEvents ?? createResumeEvents();

    const approvedPromise = new Promise<void>((resolve) => {
      this._approvedResolve = resolve;
    });

    let connectionCount = 0;

    await this.page.route(
      `**/api/incidents/${INCIDENT_ID}/stream`,
      async (route) => {
        connectionCount++;

        if (connectionCount === 1) {
          // Phase 1: send all pre-approval events
          // Set retry: 100ms so EventSource reconnects quickly for tests
          await fulfillSSE(route, pre, { retryMs: 100 });
          // Connection closes → EventSource will auto-reconnect in ~100ms
        } else if (connectionCount === 2) {
          // Phase 2: wait for approval, then send resume events
          await approvedPromise;
          await fulfillSSE(route, resume);
        }
        // Connection 3+: hang forever (no more events to send)
      },
    );
  }

  /**
   * Approval handler for live SSE tests.
   * After fulfilling the approval response, unblocks the waiting SSE reconnection.
   */
  async setupApproveDecideLive(approvalId?: string) {
    const id = approvalId ?? APPROVAL_ID;
    await this.page.route(
      `**/api/approvals/${id}/decide`,
      async (route) => {
        await route.fulfill({ json: createMockApprovalDecision({ id }) });
        // Signal the SSE handler to send resume events
        this._approvedResolve?.();
      },
    );
  }

  /** Replace SSE route with full post-approval events (requires reload) */
  async setupSSEStreamFull() {
    await this.page.unroute(`**/api/incidents/${INCIDENT_ID}/stream`);
    await this.setupSSEStream(createPostApprovalEvents());
  }

  /** POST /api/approvals/:id/decide — static (no SSE follow-up) */
  async setupApproveDecide() {
    await this.page.route(
      `**/api/approvals/${APPROVAL_ID}/decide`,
      async (route) => {
        await route.fulfill({ json: createMockApprovalDecision() });
      },
    );
  }

  /** POST /api/incidents/:id/save-to-memory */
  async setupSaveToMemory() {
    await this.page.route(
      `**/api/incidents/${INCIDENT_ID}/save-to-memory`,
      async (route) => {
        await route.fulfill({
          json: { ok: true, incident_history_id: "history-001" },
        });
      },
    );
  }

  // ── Connection & Services ──

  /** GET/POST/DELETE /api/connections and sub-routes */
  async setupConnectionRoutes(list?: Connection[]) {
    const conns = list ?? createMockConnectionList();

    // Must register more specific routes first (Playwright uses first-match)
    // POST /api/connections/:id/test
    await this.page.route("**/api/connections/*/test", async (route) => {
      await route.fulfill({
        json: { success: true, message: "Connection successful" },
      });
    });

    // DELETE /api/connections/:id
    await this.page.route("**/api/connections/*", async (route) => {
      const method = route.request().method();
      if (method === "DELETE") {
        await route.fulfill({ json: { ok: true } });
      } else {
        await route.continue();
      }
    });

    // GET (list) / POST (create) /api/connections
    await this.page.route("**/api/connections", async (route) => {
      const method = route.request().method();
      if (method === "GET") {
        await route.fulfill({ json: conns });
      } else if (method === "POST") {
        await route.fulfill({ json: createMockConnection() });
      } else {
        await route.continue();
      }
    });
  }

  /** POST /api/connections/:id/test with custom success/failure */
  async setupConnectionTest(success = true) {
    await this.page.route("**/api/connections/*/test", async (route) => {
      await route.fulfill({
        json: {
          success,
          message: success ? "Connection successful" : "Connection failed",
        },
      });
    });
  }

  /** GET /api/services/by-connection/:id, POST /api/services, DELETE /api/services/:id */
  async setupServiceRoutes(connId?: string, services?: Service[]) {
    const svcList = services ?? createMockServiceList();
    const matchConnId = connId ?? CONN_SSH_ID;

    // Catch-all for /api/services/by-connection/* — uses URL to decide response
    await this.page.route("**/api/services/by-connection/*", async (route) => {
      const url = route.request().url();
      if (url.includes(matchConnId)) {
        await route.fulfill({ json: svcList });
      } else {
        await route.fulfill({ json: [] });
      }
    });

    // DELETE /api/services/:id
    await this.page.route("**/api/services/*", async (route) => {
      const method = route.request().method();
      if (method === "DELETE") {
        await route.fulfill({ json: { ok: true } });
      } else {
        await route.continue();
      }
    });

    // POST /api/services (create)
    await this.page.route("**/api/services", async (route) => {
      const method = route.request().method();
      if (method === "POST") {
        await route.fulfill({
          json: {
            id: "svc-new",
            connection_id: matchConnId,
            name: "new-service",
            port: null,
            namespace: null,
            status: "unknown",
            discovery_method: "manual",
            created_at: "2026-03-16T10:00:00Z",
            updated_at: "2026-03-16T10:00:00Z",
          },
        });
      } else {
        await route.continue();
      }
    });
  }

  /** POST /api/services/discover/:id */
  async setupDiscoverServices(connId?: string, result?: { discovered: number; services: Service[] }) {
    const matchConnId = connId ?? CONN_SSH_ID;
    const discoverResult = result ?? {
      discovered: 3,
      services: createMockServiceList(),
    };

    await this.page.route(
      `**/api/services/discover/${matchConnId}`,
      async (route) => {
        await route.fulfill({ json: discoverResult });
      },
    );
  }

  /** GET/POST /api/incidents/:id/messages */
  async setupMessages() {
    await this.page.route(
      `**/api/incidents/${INCIDENT_ID}/messages`,
      async (route) => {
        const method = route.request().method();
        if (method === "GET") {
          await route.fulfill({ json: [] });
        } else if (method === "POST") {
          await route.fulfill({
            json: {
              id: "msg-001",
              incident_id: INCIDENT_ID,
              role: "user",
              event_type: "user_message",
              content: "test",
              metadata_json: null,
              created_at: "2026-03-16T10:10:00Z",
            },
          });
        } else {
          await route.continue();
        }
      },
    );
  }
}

export const test = base.extend<{ mockApi: MockApiHelper }>({
  mockApi: async ({ page }, use) => {
    await use(new MockApiHelper(page));
  },
});

export { expect } from "@playwright/test";
