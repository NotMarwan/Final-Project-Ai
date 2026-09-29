"use client"

import { useEffect, type RefObject } from "react"

const FOCUSABLE_SELECTOR = [
  "a[href]",
  "button:not([disabled])",
  "input:not([disabled])",
  "select:not([disabled])",
  "textarea:not([disabled])",
  "[tabindex]:not([tabindex='-1'])",
].join(", ")

/** Keeps Tab focus inside a modal container and restores focus to whatever
 *  opened it when the modal closes (ARIA APG dialog pattern). The container
 *  needs `tabIndex={-1}` so it can receive focus when it holds nothing
 *  focusable; screens that must not scroll behind the modal also lock the
 *  document while `active` is true. */
export function useModalFocus<T extends HTMLElement>(containerRef: RefObject<T | null>, active: boolean) {
  useEffect(() => {
    if (!active) return
    const container = containerRef.current
    if (!container) return
    const previous = document.activeElement instanceof HTMLElement ? document.activeElement : null
    const focusable = () => Array.from(container.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR))
      .filter((node) => node.offsetParent !== null || node === document.activeElement)
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "Tab") return
      const nodes = focusable()
      if (nodes.length === 0) { event.preventDefault(); container.focus(); return }
      const first = nodes[0]
      const last = nodes[nodes.length - 1]
      const current = document.activeElement
      if (event.shiftKey && (current === first || !container.contains(current))) { event.preventDefault(); last.focus() }
      else if (!event.shiftKey && current === last) { event.preventDefault(); first.focus() }
    }
    const firstFocusable = focusable()[0]
    ;(firstFocusable ?? container).focus()
    container.addEventListener("keydown", onKeyDown)
    return () => {
      container.removeEventListener("keydown", onKeyDown)
      if (previous && previous.isConnected) previous.focus()
    }
  }, [containerRef, active])
}
