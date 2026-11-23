import { forwardRef, useState } from 'react';
import { primaryControl } from './controlStyles';
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

interface PasswordFieldProps extends Omit<TextFieldProps, 'type'> {
  visibleLabel?: string;
}

export const PasswordField = forwardRef<HTMLInputElement, PasswordFieldProps>(function PasswordField(
  { id, label, error, helper, visibleLabel = label, ...inputProps },
  ref,
) {
  const [visible, setVisible] = useState(false);
  return (
    <div>
      <label htmlFor={id} className="block text-sm font-medium tracking-wide text-ink mb-1">
        {label}
      </label>
      <div className="relative">
        <input
          id={id}
          ref={ref}
          type={visible ? 'text' : 'password'}
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? `${id}-error` : helper ? `${id}-helper` : undefined}
          className="w-full rounded-control border border-line bg-paper px-3 py-2.5 pr-11 text-sm text-ink focus:border-ink focus:outline-none"
          {...inputProps}
        />
        <button
          type="button"
          aria-label={`${visibleLabel} ${visible ? '숨기기' : '보기'}`}
          aria-pressed={visible}
          onClick={() => setVisible((current) => !current)}
          className="absolute inset-y-0 right-0 flex w-11 items-center justify-center text-muted hover:text-ink focus:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ink"
        >
          {visible ? (
            <svg aria-hidden="true" viewBox="0 0 24 24" className="h-5 w-5 fill-none stroke-current" strokeWidth="1.8">
              <path d="m3 3 18 18M10.6 10.7a2 2 0 0 0 2.7 2.7M9.9 4.3A10.8 10.8 0 0 1 12 4c5.5 0 9 5 9 5a17.7 17.7 0 0 1-3.1 3.5M6.2 6.2C4.2 7.6 3 9 3 9s3.5 5 9 5c.7 0 1.4-.1 2-.2" />
            </svg>
          ) : (
            <svg aria-hidden="true" viewBox="0 0 24 24" className="h-5 w-5 fill-none stroke-current" strokeWidth="1.8">
              <path d="M3 12s3.5-5 9-5 9 5 9 5-3.5 5-9 5-9-5-9-5Z" /><circle cx="12" cy="12" r="2.5" />
            </svg>
          )}
        </button>
      </div>
      {error && <p id={`${id}-error`} role="alert" className="mt-1 text-xs text-danger">{error}</p>}
      {!error && helper && <p id={`${id}-helper`} className="mt-1 text-xs text-muted">{helper}</p>}
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
      className={`${primaryControl} w-full`}
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
