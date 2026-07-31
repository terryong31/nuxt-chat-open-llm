CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER AS $$
BEGIN
  INSERT INTO public.users (id, email, name, avatar, username, provider, provider_id)
  VALUES (
    NEW.id,
    NEW.email,
    '',
    '',
    split_part(COALESCE(NEW.email, 'user@local.host'), '@', 1),
    'email',
    NEW.id::text
  )
  ON CONFLICT (id) DO NOTHING;
  RETURN NEW;
EXCEPTION WHEN OTHERS THEN
  RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;
