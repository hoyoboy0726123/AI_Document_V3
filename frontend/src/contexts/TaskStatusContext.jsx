/**
 * TaskStatusContext
 * 全域追蹤背景任務（pdf_analyze / vectorize / vl_vectorize）的狀態，每 4 秒 poll 一次。
 * 任務 ID 存在 localStorage key: "activeTasks" (JSON array)
 */
import React, { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import apiClient from "../services/api";

const TaskStatusContext = createContext(null);

const STORAGE_KEY = "activeTasks"; // [{task_id, document_id, document_title, task_type}]
const POLL_INTERVAL = 4000;

export const TaskStatusProvider = ({ children }) => {
  const [tasks, setTasks] = useState(() => {
    try {
      return JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "[]");
    } catch {
      return [];
    }
  });
  // taskStatuses: { [task_id]: TaskRead }
  const [taskStatuses, setTaskStatuses] = useState({});
  // onComplete callbacks: { [task_id]: (taskData) => void }
  const callbacksRef = useRef({});

  const _persist = (list) => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(list));
  };

  const addTask = useCallback((taskEntry, onCompleteCallback) => {
    setTasks((prev) => {
      const next = [...prev.filter((t) => t.task_id !== taskEntry.task_id), taskEntry];
      _persist(next);
      return next;
    });
    if (onCompleteCallback) {
      callbacksRef.current[taskEntry.task_id] = onCompleteCallback;
    }
  }, []);

  const removeTask = useCallback((taskId) => {
    delete callbacksRef.current[taskId];
    setTasks((prev) => {
      const next = prev.filter((t) => t.task_id !== taskId);
      _persist(next);
      return next;
    });
    setTaskStatuses((prev) => {
      const { [taskId]: _, ...rest } = prev;
      return rest;
    });
  }, []);

  // Poll active tasks
  useEffect(() => {
    const poll = async () => {
      const activeTasks = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "[]");
      if (!activeTasks.length) return;

      const results = await Promise.allSettled(
        activeTasks.map((t) => apiClient.get(`tasks/${t.task_id}`))
      );

      const newStatuses = {};
      results.forEach((result, idx) => {
        const entry = activeTasks[idx];
        if (result.status === "fulfilled") {
          const data = result.value.data;
          newStatuses[entry.task_id] = data;

          // 觸發 onComplete callback（completed 或 failed 時各呼叫一次）
          const isDone = data.status === "completed" || data.status === "failed";
          const cb = callbacksRef.current[entry.task_id];
          if (isDone && cb) {
            cb(data);
            delete callbacksRef.current[entry.task_id];
          }
        }
      });

      setTaskStatuses((prev) => ({ ...prev, ...newStatuses }));
    };

    const timer = setInterval(poll, POLL_INTERVAL);
    poll(); // immediate first poll
    return () => clearInterval(timer);
  }, []);

  return (
    <TaskStatusContext.Provider value={{ tasks, taskStatuses, addTask, removeTask }}>
      {children}
    </TaskStatusContext.Provider>
  );
};

export const useTaskStatus = () => {
  const ctx = useContext(TaskStatusContext);
  if (!ctx) throw new Error("useTaskStatus must be used within TaskStatusProvider");
  return ctx;
};
