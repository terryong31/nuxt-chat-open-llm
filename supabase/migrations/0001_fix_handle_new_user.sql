-- Fix handle_new_user trigger function to be null-safe for dev and auth user signups
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER AS $$
BEGIN
  INSERT INTO public.users (id, email, name, avatar, username, provider, provider_id)
  VALUES (
    NEW.id,
    NEW.email,
    COALESCE(
      CASE WHEN NEW.raw_user_meta_data IS NOT NULL THEN NEW.raw_user_meta_data->>'full_name' ELSE NULL END,
      CASE WHEN NEW.raw_user_meta_data IS NOT NULL THEN NEW.raw_user_meta_data->>'name' ELSE NULL END,
      ''
    ),
    COALESCE(
      CASE WHEN NEW.raw_user_meta_data IS NOT NULL THEN NEW.raw_user_meta_data->>'avatar_url' ELSE NULL END,
      CASE WHEN NEW.raw_user_meta_data IS NOT NULL THEN NEW.raw_user_meta_data->>'avatar' ELSE NULL END,
      ''
    ),
    COALESCE(
      CASE WHEN NEW.raw_user_meta_data IS NOT NULL THEN NEW.raw_user_meta_data->>'preferred_username' ELSE NULL END,
      CASE WHEN NEW.raw_user_meta_data IS NOT NULL THEN NEW.raw_user_meta_data->>'user_name' ELSE NULL END,
      split_part(COALESCE(NEW.email, 'user@local.host'), '@', 1)
    ),
    COALESCE(
      CASE WHEN NEW.app_metadata IS NOT NULL THEN NEW.app_metadata->>'provider' ELSE NULL END,
      'email'
    ),
    COALESCE(
      CASE WHEN NEW.raw_user_meta_data IS NOT NULL THEN NEW.raw_user_meta_data->>'provider_id' ELSE NULL END,
      NEW.id::text
    )
  )
  ON CONFLICT (id) DO UPDATE SET
    email = EXCLUDED.email,
    name = EXCLUDED.name,
    avatar = EXCLUDED.avatar,
    username = EXCLUDED.username;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;
