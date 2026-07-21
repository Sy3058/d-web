import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { signupSchema, type SignupInput } from '../../lib/validation';
import { api, ApiError, extractDetail } from '../../lib/api';
import { TextField, SubmitButton, FormError } from '../ui/forms';

export default function SignupForm() {
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<SignupInput>({ resolver: zodResolver(signupSchema) });
  const [formError, setFormError] = useState('');
  const [done, setDone] = useState(false);

  async function onSubmit(data: SignupInput) {
    setFormError('');
    try {
      await api.post('/auth/signup', data);
      setDone(true);
    } catch (err) {
      if (err instanceof ApiError) {
        setFormError(
          extractDetail(err) ?? '가입 처리 중 문제가 발생했어요. 잠시 후 다시 시도해 주세요.',
        );
      } else {
        setFormError('네트워크 오류로 가입에 실패했어요. 잠시 후 다시 시도해 주세요.');
      }
    }
  }

  if (done) {
    return (
      <div className="rounded-control border border-line px-6 py-8 text-center">
        <p className="text-sm font-medium text-ink mb-2">메일을 보냈어요</p>
        <p className="text-sm text-muted">
          입력하신 주소로 인증 메일을 보냈어요. 메일의 링크를 눌러 인증을 완료해 주세요.
        </p>
      </div>
    );
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
        id="nickname"
        label="닉네임"
        type="text"
        autoComplete="nickname"
        error={errors.nickname?.message}
        {...register('nickname')}
      />
      <TextField
        id="password"
        label="비밀번호"
        type="password"
        autoComplete="new-password"
        error={errors.password?.message}
        helper="8자 이상, 영문·숫자·특수문자를 각각 포함하세요."
        {...register('password')}
      />
      {formError && <FormError message={formError} />}
      <SubmitButton disabled={isSubmitting}>
        {isSubmitting ? '처리 중...' : '회원가입'}
      </SubmitButton>
    </form>
  );
}
