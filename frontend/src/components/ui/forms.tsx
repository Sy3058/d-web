import { forwardRef } from 'react';
import { controlBase } from './controlStyles';
import type { ComponentPropsWithoutRef, ReactNode } from 'react';

interface TextFieldProps extends ComponentPropsWithoutRef<'input'> {
  id: string;
  label: string;
  error?: string;
  helper?: string;
}

export const TextField = forwardRef<HTMLInputElement, TextFieldProps>(function TextField(
  { id, label, error, helper, ...inputProps },
  ref,
) {
  return (
    <div>
      <label htmlFor={id} className="block text-sm font-medium tracking-wide text-ink mb-1">
        {label}
      </label>
      <input
        id={id}
        ref={ref}
        aria-invalid={error ? true : undefined}
        aria-describedby={error ? `${id}-error` : helper ? `${id}-helper` : undefined}
        className="w-full rounded-control border border-line px-3 py-2.5 text-sm text-ink bg-paper focus:border-ink focus:outline-none"
        {...inputProps}
      />
      {error && (
        <p id={`${id}-error`} role="alert" className="mt-1 text-xs text-danger">
          {error}
        </p>
      )}
      {!error && helper && (
        <p id={`${id}-helper`} className="mt-1 text-xs text-muted">
          {helper}
        </p>
      )}
    </div>
  );
});

interface SubmitButtonProps {
  disabled?: boolean;
  children: ReactNode;
}

export function SubmitButton({ disabled, children }: SubmitButtonProps) {
  return (
    <button
      type="submit"
      disabled={disabled}
      className={`${controlBase} w-full bg-ink px-4 py-2.5 text-paper tracking-wide hover:bg-ink-strong`}
    >
      {children}
    </button>
  );
}

interface FormErrorProps {
  message: string;
}

export function FormError({ message }: FormErrorProps) {
  return (
    <div role="alert" className="border-l-2 border-danger pl-4 py-2 text-sm text-danger">
      {message}
    </div>
  );
}

interface FormNoticeProps {
  message: string;
}

export function FormNotice({ message }: FormNoticeProps) {
  return (
    <div className="rounded-control border border-line px-4 py-3 text-sm text-ink">
      {message}
    </div>
  );
}
