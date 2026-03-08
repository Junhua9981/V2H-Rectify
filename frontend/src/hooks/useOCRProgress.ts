/** useOCRProgress — polls status + listens to WebSocket progress. */

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

  const cleanup = useCallback(() => {
    wsRef.current?.close();
    wsRef.current = null;
    if (pollRef.current) clearInterval(pollRef.current);
    pollRef.current = null;
  }, []);

  useEffect(() => {
    if (!taskId) {
      const timer = window.setTimeout(() => {
        setState(INITIAL);
      }, 0);
      return () => {
        window.clearTimeout(timer);
      };
    }

    // WebSocket for real-time progress
    const ws = connectProgressWS(taskId);
    wsRef.current = ws;

    ws.onmessage = (ev) => {
      try {
        const msg: WSProgressMessage = JSON.parse(ev.data);
        setState((s) => ({ ...s, stage: msg.stage, progress: msg.progress }));
      } catch {
        // ignore malformed messages
      }
    };

    // Polling fallback (every 2s)
    pollRef.current = setInterval(async () => {
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
        if (res.status === "completed" || res.status === "failed") {
          cleanup();
        }
      } catch {
        // ignore transient errors
      }
    }, 2000);

    return cleanup;
  }, [taskId, cleanup]);

  return state;
}
