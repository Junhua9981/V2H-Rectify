/** useBatchProgress — WebSocket + polling for batch OCR progress. */

import { useCallback, useEffect, useRef, useState } from "react";
import { connectBatchProgressWS, pollBatchStatus } from "../lib/api";
import type { BatchStatusResponse, OCRStatusResponse, WSBatchProgressMessage } from "../lib/types";

interface BatchProgressState {
  total: number;
  completed: number;
  failed: number;
  processing: number;
  progress: number;
  tasks: OCRStatusResponse[];
  done: boolean;
}

const INITIAL: BatchProgressState = {
  total: 0,
  completed: 0,
  failed: 0,
  processing: 0,
  progress: 0,
  tasks: [],
  done: false,
};

export function useBatchProgress(batchId: string | null) {
  const [state, setState] = useState<BatchProgressState>(INITIAL);
  const wsRef = useRef<WebSocket | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const doneRef = useRef(false);

  const cleanup = useCallback(() => {
    wsRef.current?.close();
    wsRef.current = null;
    if (pollRef.current) clearInterval(pollRef.current);
    pollRef.current = null;
  }, []);

  const applyBatchStatus = useCallback((res: BatchStatusResponse) => {
    const isDone = res.completed + res.failed >= res.total && res.total > 0;
    setState({
      total: res.total,
      completed: res.completed,
      failed: res.failed,
      processing: res.processing,
      progress: res.progress,
      tasks: res.tasks,
      done: isDone,
    });
    if (isDone) doneRef.current = true;
  }, []);

  useEffect(() => {
    if (!batchId) {
      setState(INITIAL);
      return;
    }

    doneRef.current = false;

    // WebSocket for live batch-level progress
    const ws = connectBatchProgressWS(batchId);
    wsRef.current = ws;

    ws.onmessage = (ev) => {
      try {
        const msg: WSBatchProgressMessage = JSON.parse(ev.data);
        setState((s) => ({
          ...s,
          progress: msg.progress,
          completed: msg.completed,
          failed: msg.failed,
          total: msg.total,
          done: msg.status === "completed",
        }));
        if (msg.status === "completed") {
          // Fetch full results
          pollBatchStatus(batchId).then(applyBatchStatus).catch(() => {});
        }
      } catch {
        // ignore
      }
    };

    // Polling fallback
    pollRef.current = setInterval(async () => {
      if (doneRef.current) return;
      try {
        const res = await pollBatchStatus(batchId);
        applyBatchStatus(res);
        if (doneRef.current) cleanup();
      } catch {
        // ignore
      }
    }, 3000);

    return cleanup;
  }, [batchId, cleanup, applyBatchStatus]);

  return state;
}
