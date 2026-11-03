import {
  AfterViewInit,
  Component,
  ElementRef,
  OnDestroy,
  input,
  output,
  viewChild,
} from '@angular/core';
import { HlmButtonImports } from '@spartan-ng/helm/button';
import { TranslatePipe } from '../core/i18n';

let nextId = 0;

/**
 * Modal built on the native <dialog> element: it traps focus, closes on Escape and returns focus
 * to the control that opened it. It never closes on a click outside, so nothing is lost by
 * accident. The parent creates it with @if and removes it when `closed` fires.
 */
@Component({
  selector: 'app-modal',
  imports: [HlmButtonImports, TranslatePipe],
  template: `
    <dialog
      #dialog
      class="bg-card text-card-foreground border-border m-auto w-[min(34rem,calc(100vw-2rem))] rounded-lg border p-6 shadow-lg backdrop:bg-black/40"
      [attr.aria-labelledby]="titleId"
      (close)="closed.emit()"
    >
      <div class="mb-4 flex items-start justify-between gap-4">
        <h2 [id]="titleId" class="text-lg font-bold">{{ heading() }}</h2>
        <button
          hlmBtn
          variant="ghost"
          size="icon-sm"
          type="button"
          [attr.aria-label]="'common.close' | t"
          (click)="dialog.close()"
        >
          <span aria-hidden="true">×</span>
        </button>
      </div>
      <ng-content />
    </dialog>
  `,
})
export class ModalComponent implements AfterViewInit, OnDestroy {
  readonly heading = input.required<string>();
  readonly closed = output<void>();
  protected readonly titleId = `modal-title-${nextId++}`;
  private readonly dialog = viewChild.required<ElementRef<HTMLDialogElement>>('dialog');

  ngAfterViewInit(): void {
    this.dialog().nativeElement.showModal();
  }

  ngOnDestroy(): void {
    const element = this.dialog().nativeElement;
    if (element.open) {
      element.close();
    }
  }
}
