/**
 * TaskStatusContext
 * 全域追蹤背景任務（VL 解析等）的狀態，每 5 秒 poll 一次。
 * 任務 ID 存在 localStorage key: "activeTasks" (JSON array)
 */
import React, { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import apiClient from "../services/api";

const TaskStatusContext = createContext(null);

const STORAGE_KEY = "activeTasks"; // [{task_id, document_id, document_title}]
const POLL_INTERVAL = 5000;

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
  const timerRef = useRef(null);

  const persistTasks = (list) => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(list));
    setTasks(list);
  };

  const addTask = useCallback((taskEntry) => {
    setTasks((prev) => {
      const next = [...prev.filter((t) => t.task_id !== taskEntry.task_id), taskEntry];
      localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
      return next;
    });
  }, []);

  const removeTask = useCallback((taskId) => {
    setTasks((prev) => {
      const next = prev.filter((t) => t.task_id !== taskId);
      localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
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

      const pendingIds = activeTasks.map((t) => t.task_id);
      const results = await Promise.allSettled(
        pendingIds.map((id) => apiClient.get(`tasks/${id}`))
      );

      const newStatuses = {};
      const stillActive = [];

      results.forEach((result, idx) => {
        const entry = activeTasks[idx];
        if (result.status === "fulfilled") {
          const data = result.value.data;
          newStatuses[entry.task_id] = data;
          if (data.status !== "completed" && data.status !== "failed") {
            stillActive.push(entry);
          }
        } else {
          // keep if network error
          stillActive.push(entry);
        }
      });

      setTaskStatuses((prev) => ({ ...prev, ...newStatuses }));
      // Only remove completed/failed from active list after user dismisses
      // (we show completed tasks until dismissed)
    };

    timerRef.current = setInterval(poll, POLL_INTERVAL);
    poll(); // immediate first poll
    return () => clearInterval(timerRef.current);
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
