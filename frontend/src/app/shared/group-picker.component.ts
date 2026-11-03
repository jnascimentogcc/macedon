import { Component, computed, input, model } from '@angular/core';
import { TranslatePipe } from '../core/i18n';

/** Multiselect of the groups a document is shared with, as a group of checkboxes. */
@Component({
  selector: 'app-group-picker',
  imports: [TranslatePipe],
  template: `
    <fieldset class="flex flex-col gap-1.5" [attr.aria-describedby]="idPrefix() + '-help'">
      <legend class="text-sm leading-none font-medium">
        {{ 'upload.groups' | t }}
        @if (optional()) {
          <span class="text-muted-foreground">{{ 'common.optional' | t }}</span>
        }
      </legend>
      @if (choices().length) {
        <div class="flex flex-wrap gap-x-4 gap-y-1.5 pt-1.5">
          @for (group of choices(); track group) {
            <label class="flex min-h-[44px] items-center gap-2 text-sm sm:min-h-[24px]">
              <input
                type="checkbox"
                class="size-4"
                [checked]="value().includes(group)"
                (change)="toggle(group)"
              />
              {{ group }}
            </label>
          }
        </div>
      } @else {
        <p class="text-muted-foreground pt-1.5 text-sm">{{ 'upload.groupsNone' | t }}</p>
      }
      <p [id]="idPrefix() + '-help'" class="text-muted-foreground text-xs">
        {{ 'upload.groupsHelp' | t }}
      </p>
    </fieldset>
  `,
})
export class GroupPickerComponent {
  /** Groups that can be chosen. */
  readonly options = input<string[]>([]);
  /** Selected groups, two-way. */
  readonly value = model<string[]>([]);
  readonly optional = input(true);
  readonly idPrefix = input('groups');

  /** The options, plus any selected group that is no longer offered, so it can be unchecked. */
  protected readonly choices = computed(() =>
    [...new Set([...this.options(), ...this.value()])].sort(),
  );

  protected toggle(group: string): void {
    this.value.update((current) =>
      current.includes(group) ? current.filter((g) => g !== group) : [...current, group],
    );
  }
}
