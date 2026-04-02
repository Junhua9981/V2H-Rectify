/** useOCRProgress — WebSocket for live progress + polling fallback. */

import { useCallback, useEffect, useRef, useState } from "react";
import { connectProgressWS, pollOCRStatus } from "../lib/api";
import type { OCRStatusResponse, WSProgressMessage, ColumnData } from "../lib/types";

interface ProgressState {
  status: OCRStatusResponse["status"];
  progress: number;
  stage: string;
  title: string | null;
  text: string | null;
  columns: ColumnData[];
  error: string | null;
  elapsed: number | null;
}

const INITIAL: ProgressState = {
  status: "pending",
  progress: 0,
  stage: "",
  title: null,
  text: null,
  columns: [],
  error: null,
  elapsed: null,
};

export function useOCRProgress(taskId: string | null) {
  const [state, setState] = useState<ProgressState>(INITIAL);
  const wsRef = useRef<WebSocket | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const doneRef = useRef(false);

  const cleanup = useCallback(() => {
    wsRef.current?.close();
    wsRef.current = null;
    if (pollRef.current) clearInterval(pollRef.current);
    pollRef.current = null;
  }, []);

  /** Fetch final status once and update state, then stop everything. */
  const finalPoll = useCallback(
    async (taskId: string) => {
      if (doneRef.current) return;
      doneRef.current = true;
      cleanup();
      try {
        const res = await pollOCRStatus(taskId);
        setState((s) => ({
          ...s,
          status: res.status,
          title: res.title,
          text: res.text,
          columns: res.columns ?? [],
          error: res.error,
          elapsed: res.elapsed_seconds,
          progress: res.progress,
        }));
      } catch {
        // ignore — polling will still catch it on next tick if WS fired too early
      }
    },
    [cleanup],
  );

  useEffect(() => {
    if (!taskId) {
      const timer = window.setTimeout(() => setState(INITIAL), 0);
      return () => window.clearTimeout(timer);
    }

    doneRef.current = false;

    // WebSocket — primary channel for live progress
    const ws = connectProgressWS(taskId);
    wsRef.current = ws;

    ws.onmessage = (ev) => {
      try {
        const msg: WSProgressMessage = JSON.parse(ev.data);
        setState((s) => ({ ...s, stage: msg.stage, progress: msg.progress }));

        if (msg.status === "completed" || msg.status === "failed") {
          // Backend signals done → fetch full result immediately, no need to wait for poll.
          finalPoll(taskId);
        }
      } catch {
        // ignore malformed messages
      }
    };

    // Polling fallback — catches cases where WS never arrives (proxy issues, etc.)
    pollRef.current = setInterval(async () => {
      if (doneRef.current) return;
      try {
        const res = await pollOCRStatus(taskId);
        setState((s) => ({
          ...s,
          status: res.status,
          title: res.title,
          text: res.text,
          columns: res.columns ?? [],
          error: res.error,
          elapsed: res.elapsed_seconds,
          // Only overwrite progress from poll if WS hasn't given us a higher value.
          progress: Math.max(s.progress, res.progress),
        }));
        if (res.status === "completed" || res.status === "failed") {
          doneRef.current = true;
          cleanup();
        }
      } catch {
        // ignore transient errors
      }
    }, 3000);

    return cleanup;
  }, [taskId, cleanup, finalPoll]);

  return state;
}
