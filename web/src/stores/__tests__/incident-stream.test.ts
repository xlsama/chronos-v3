import { describe, it, expect, beforeEach } from "vitest";
import { useIncidentStreamStore } from "../incident-stream";

describe("incident-stream store", () => {
  beforeEach(() => {
    useIncidentStreamStore.getState().reset();
  });

  it("should start with empty state", () => {
    const state = useIncidentStreamStore.getState();
    expect(state.events).toEqual([]);
    expect(state.historyAgentState.events).toEqual([]);
    expect(state.kbAgentState.events).toEqual([]);
    expect(state.isConnected).toBe(false);
    expect(state.thinkingContent).toBe("");
    expect(state.historyAgentState.thinkingContent).toBe("");
    expect(state.kbAgentState.thinkingContent).toBe("");
  });

  it("should add events", () => {
    const { addEvent } = useIncidentStreamStore.getState();
    addEvent({
      event_type: "thinking",
      data: { content: "Analyzing..." },
      timestamp: "2026-01-01T00:00:00Z",
    });

    expect(useIncidentStreamStore.getState().events).toHaveLength(1);
    expect(useIncidentStreamStore.getState().events[0].event_type).toBe("thinking");
  });

  it("should append thinking content", () => {
    const { appendThinking } = useIncidentStreamStore.getState();
    appendThinking("Hello ");
    appendThinking("World");

    expect(useIncidentStreamStore.getState().thinkingContent).toBe("Hello World");
  });

  it("should clear thinking content", () => {
    const { appendThinking, clearThinking } = useIncidentStreamStore.getState();
    appendThinking("Hello");
    clearThinking();

    expect(useIncidentStreamStore.getState().thinkingContent).toBe("");
  });

  it("should set connected state", () => {
    const { setConnected } = useIncidentStreamStore.getState();
    setConnected(true);
    expect(useIncidentStreamStore.getState().isConnected).toBe(true);

    setConnected(false);
    expect(useIncidentStreamStore.getState().isConnected).toBe(false);
  });

  it("should reset all state", () => {
    const state = useIncidentStreamStore.getState();
    state.addEvent({
      event_type: "test",
      data: {},
      timestamp: "2026-01-01T00:00:00Z",
    });
    state.appendThinking("test");
    state.appendSubAgentThinking("history", "sub-test");
    state.setConnected(true);

    state.reset();

    const newState = useIncidentStreamStore.getState();
    expect(newState.events).toEqual([]);
    expect(newState.historyAgentState.events).toEqual([]);
    expect(newState.kbAgentState.events).toEqual([]);
    expect(newState.thinkingContent).toBe("");
    expect(newState.historyAgentState.thinkingContent).toBe("");
    expect(newState.kbAgentState.thinkingContent).toBe("");
    expect(newState.isConnected).toBe(false);
  });

  it("should append and flush sub agent thinking content", () => {
    const { appendSubAgentThinking, flushSubAgentThinking } =
      useIncidentStreamStore.getState();
    appendSubAgentThinking("history", "Searching ");
    appendSubAgentThinking("history", "history...");

    expect(
      useIncidentStreamStore.getState().historyAgentState.thinkingContent,
    ).toBe("Searching history...");

    flushSubAgentThinking("history", "2026-01-01T00:00:00Z");
    expect(
      useIncidentStreamStore.getState().historyAgentState.thinkingContent,
    ).toBe("");
    expect(
      useIncidentStreamStore.getState().historyAgentState.events,
    ).toHaveLength(1);
  });
});
