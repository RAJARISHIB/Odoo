import {
  ChangeDetectionStrategy,
  Component,
  ElementRef,
  computed,
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

/**
 * Global search in the topbar.
 *
 * Replaces a placeholder-only input that had a `/` hint, no handler and no
 * results — an affordance that promised a feature the app did not have.
 *
 * Keyboard is the point of a search like this: `/` from anywhere focuses it,
 * arrows walk the flattened result list across group boundaries, Enter opens
 * the highlighted row and Escape hands focus back to the page.
 */
@Component({
  selector: 'app-global-search',
  imports: [ReactiveFormsModule, Icon],
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: {
    '(document:click)': 'onDocumentClick($event)',
    '(document:keydown)': 'onDocumentKeydown($event)',
  },
  templateUrl: './global-search.html',
  styleUrl: './global-search.scss',
})
export class GlobalSearch {
  private readonly search = inject(Search);
  private readonly router = inject(Router);
  protected readonly layout = inject(Layout);
  private readonly host = inject<ElementRef<HTMLElement>>(ElementRef);
  private readonly field = viewChild<ElementRef<HTMLInputElement>>('field');

  protected readonly term = new FormControl('', { nonNullable: true });
  protected readonly open = signal(false);
  /** Compact only: whether the collapsed trigger has been swapped for the bar. */
  protected readonly expanded = signal(false);
  protected readonly loading = signal(false);
  /** Index into `flat()`, or -1 when nothing is highlighted. */
  protected readonly cursor = signal(-1);

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
    const all = this.hits();
    return GROUP_ORDER.map((group) => ({
      group,
      label: GROUP_LABELS[group],
      hits: all.filter((hit) => hit.group === group),
    })).filter((section) => section.hits.length > 0);
  });

  /** The same hits in render order, so one index can walk every group. */
  protected readonly flat = computed(() => this.sections().flatMap((section) => section.hits));

  protected readonly hasQuery = computed(() => this.value().trim().length >= 2);

  protected readonly showPanel = computed(
    () => this.open() && (this.hasQuery() || this.flat().length > 0),
  );

  protected isActive(hit: SearchHit): boolean {
    return this.flat()[this.cursor()]?.id === hit.id;
  }

  // -- open / close --------------------------------------------------------
  protected onFocus(): void {
    this.open.set(true);
  }

  protected close(): void {
    this.open.set(false);
    this.cursor.set(-1);
  }

  /** Compact: swap the trigger for the bar and focus it once it exists. */
  protected expand(): void {
    this.expanded.set(true);
    this.open.set(true);
    // The input is created by this same change, so focusing has to wait for
    // the render rather than happening in this frame.
    queueMicrotask(() => this.field()?.nativeElement.focus());
  }

  protected collapse(): void {
    this.expanded.set(false);
    this.term.setValue('');
    this.close();
  }

  protected onDocumentClick(event: MouseEvent): void {
    if (!this.open() && !this.expanded()) return;
    if (this.host.nativeElement.contains(event.target as Node)) return;
    this.close();
    // On compact the bar covers the topbar, so an outside tap has to put the
    // trigger back as well as dismiss the results.
    if (this.layout.isCompact()) this.collapse();
  }

  /**
   * `/` focuses the field from anywhere, the way it does in most tools with a
   * search box — but only when the user is not already typing into something,
   * otherwise it would swallow the character.
   */
  protected onDocumentKeydown(event: KeyboardEvent): void {
    if (event.key !== '/' || event.metaKey || event.ctrlKey || event.altKey) return;

    const target = event.target as HTMLElement | null;
    const tag = target?.tagName;
    if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || target?.isContentEditable) {
      return;
    }

    event.preventDefault();
    this.field()?.nativeElement.focus();
    this.open.set(true);
  }

  // -- keyboard within the field -------------------------------------------
  protected onKeydown(event: KeyboardEvent): void {
    const results = this.flat();

    switch (event.key) {
      case 'ArrowDown':
        if (!results.length) return;
        event.preventDefault();
        this.open.set(true);
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
        if (this.term.value) {
          this.term.setValue('');
        } else if (this.layout.isCompact()) {
          this.collapse();
        } else {
          this.close();
          this.field()?.nativeElement.blur();
        }
        break;
    }
  }

  protected go(hit: SearchHit): void {
    this.close();
    this.expanded.set(false);
    this.term.setValue('');
    this.router.navigate([hit.link], { queryParams: hit.queryParams });
  }
}
