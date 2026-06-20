import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { loginSchema, type LoginInput } from '../../lib/validation';
import { api, ApiError, extractDetail } from '../../lib/api';
import { TextField, SubmitButton, FormError } from './ui';

export default function LoginForm() {
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<LoginInput>({ resolver: zodResolver(loginSchema) });
  const [formError, setFormError] = useState('');

  async function onSubmit(data: LoginInput) {
    setFormError('');
    try {
      await api.post('/auth/login', data);
      window.location.href = '/my';
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.status === 429) {
          setFormError('잠시 후 다시 시도해 주세요.');
        } else if (err.status === 401) {
          setFormError('이메일 또는 비밀번호가 올바르지 않습니다.');
        } else {
          setFormError(
            extractDetail(err) ?? '로그인 중 문제가 발생했어요. 잠시 후 다시 시도해 주세요.',
          );
        }
      } else {
        setFormError('네트워크 오류가 발생했어요. 잠시 후 다시 시도해 주세요.');
      }
    }
  }

  return (
    <form onSubmit={handleSubmit(onSubmit)} noValidate className="space-y-5">
      <TextField
        id="email"
        label="이메일"
        type="email"
        autoComplete="email"
        error={errors.email?.message}
        {...register('email')}
      />
      <TextField
        id="password"
        label="비밀번호"
        type="password"
        autoComplete="current-password"
        error={errors.password?.message}
        {...register('password')}
      />
      {formError && <FormError message={formError} />}
      <SubmitButton disabled={isSubmitting}>
        {isSubmitting ? '처리 중...' : '로그인'}
      </SubmitButton>
    </form>
  );
}
