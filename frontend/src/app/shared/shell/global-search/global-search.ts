import {
  ChangeDetectionStrategy,
  Component,
  ElementRef,
  computed,
  effect,
  inject,
  signal,
  viewChild,
} from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { FormControl, ReactiveFormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { debounceTime, distinctUntilChanged, switchMap, tap } from 'rxjs/operators';
import { of } from 'rxjs';

import {
  GROUP_LABELS,
  GROUP_ORDER,
  Search,
  SearchGroup,
  SearchHit,
} from '../../../core/services/search';
import { Layout } from '../../../core/services/layout';
import { Icon } from '../../icon/icon';

interface Section {
  group: SearchGroup;
  label: string;
  hits: SearchHit[];
}

const MAC = typeof navigator !== 'undefined' && /Mac|iPhone|iPad/.test(navigator.platform ?? '');

/**
 * Global search: a topbar trigger that opens a command-palette overlay.
 *
 * `Ctrl+K` (`Cmd+K` on macOS) opens it from anywhere in the app, the way it
 * does in most tools with a command palette. Arrow keys walk the flattened
 * result list across group boundaries, Enter opens the highlighted row and
 * Escape hands focus back to the page.
 */
@Component({
  selector: 'app-global-search',
  imports: [ReactiveFormsModule, Icon],
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: {
    '(document:keydown)': 'onDocumentKeydown($event)',
  },
  templateUrl: './global-search.html',
  styleUrl: './global-search.scss',
})
export class GlobalSearch {
  private readonly search = inject(Search);
  private readonly router = inject(Router);
  protected readonly layout = inject(Layout);
  private readonly field = viewChild<ElementRef<HTMLInputElement>>('field');

  protected readonly shortcutKey = MAC ? '⌘K' : 'Ctrl K';

  protected readonly term = new FormControl('', { nonNullable: true });
  protected readonly open = signal(false);
  protected readonly loading = signal(false);
  /** Index into `flat()`, or -1 when nothing is highlighted. */
  protected readonly cursor = signal(-1);

  constructor() {
    // The overlay covers the page, so the page behind it must not scroll.
    effect(() => document.body.classList.toggle('search-open', this.open()));
  }

  /**
   * The live query as a signal.
   *
   * `computed()` cannot read `FormControl.value` — it is a plain property, not
   * a signal, so a computed that reads it is evaluated once and then never
   * invalidated. Everything reactive below goes through this instead.
   */
  protected readonly value = toSignal(this.term.valueChanges, {
    initialValue: this.term.value,
  });

  protected readonly hasQuery = computed(() => this.value().trim().length >= 2);

  private readonly hits = toSignal(
    this.term.valueChanges.pipe(
      debounceTime(180),
      distinctUntilChanged(),
      tap(() => this.cursor.set(-1)),
      switchMap((value) => {
        if (value.trim().length < 2) {
          this.loading.set(false);
          return of<SearchHit[]>([]);
        }
        this.loading.set(true);
        // `switchMap` already drops the in-flight request when a newer
        // keystroke arrives, so a slow group can never overwrite fresh results.
        return this.search.query(value).pipe(tap(() => this.loading.set(false)));
      }),
    ),
    { initialValue: [] as SearchHit[] },
  );

  protected readonly sections = computed<Section[]>(() => {
    if (!this.hasQuery()) {
      const quick = this.search.quickLinks();
      return quick.length ? [{ group: 'go' as const, label: 'Quick links', hits: quick }] : [];
    }

    const all = this.hits();
    return GROUP_ORDER.map((group) => ({
      group,
      label: GROUP_LABELS[group],
      hits: all.filter((hit) => hit.group === group),
    })).filter((section) => section.hits.length > 0);
  });

  /** The same hits in render order, so one index can walk every group. */
  protected readonly flat = computed(() => this.sections().flatMap((section) => section.hits));

  protected isActive(hit: SearchHit): boolean {
    return this.flat()[this.cursor()]?.id === hit.id;
  }

  // -- open / close --------------------------------------------------------
  protected openPalette(): void {
    this.open.set(true);
    // The field only renders once the overlay is in the DOM, so focusing it
    // has to wait for that render rather than happening in this frame.
    queueMicrotask(() => this.field()?.nativeElement.focus());
  }

  protected close(): void {
    this.open.set(false);
    this.cursor.set(-1);
  }

  protected onBackdropClick(event: MouseEvent): void {
    if (event.target === event.currentTarget) this.close();
  }

  /** `Ctrl+K` / `Cmd+K` toggles the palette from anywhere in the app. */
  protected onDocumentKeydown(event: KeyboardEvent): void {
    const mod = MAC ? event.metaKey : event.ctrlKey;
    if (!mod || event.key.toLowerCase() !== 'k') return;

    event.preventDefault();
    if (this.open()) {
      this.close();
    } else {
      this.openPalette();
    }
  }

  // -- keyboard within the field -------------------------------------------
  protected onKeydown(event: KeyboardEvent): void {
    const results = this.flat();

    switch (event.key) {
      case 'ArrowDown':
        if (!results.length) return;
        event.preventDefault();
        this.cursor.update((i) => (i + 1) % results.length);
        break;

      case 'ArrowUp':
        if (!results.length) return;
        event.preventDefault();
        this.cursor.update((i) => (i <= 0 ? results.length - 1 : i - 1));
        break;

      case 'Enter': {
        // No highlight yet: Enter takes the first result, which is what
        // pressing it immediately after typing is expected to do.
        const hit = results[this.cursor()] ?? results[0];
        if (!hit) return;
        event.preventDefault();
        this.go(hit);
        break;
      }

      case 'Escape':
        event.preventDefault();
        // First keystroke clears the query, mirroring the native `<search>`
        // cancel button; the second closes the whole palette.
        if (this.term.value) {
          this.term.setValue('');
        } else {
          this.close();
        }
        break;
    }
  }

  protected go(hit: SearchHit): void {
    this.close();
    this.term.setValue('');
    this.router.navigate([hit.link], { queryParams: hit.queryParams });
  }
}
