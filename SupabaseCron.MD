Dùng Supabase Cron gọi API Vercel mỗi 30 giây, không cần thêm Edge Function.
Lưu ý: code hiện tại vẫn ép nhịp tài khoản tối thiểu 60 giây. Hướng dẫn này tạo lịch gọi 30 giây; muốn auto thực sự hỗ trợ nhịp đó còn phải sửa backend/UI và kiểm tra khóa chống chạy trùng.
1. Chuẩn bị Vercel
Trong Environment Variables, cấu hình:
CRON_SECRET=<secret-ngẫu-nhiên-của-bạn>
Redeploy nếu vừa thay biến môi trường.
Endpoint cần gọi:
https://TEN-MIEN-CUA-BAN/api/v1/cron/automation
Dùng domain production, không dùng preview URL. Endpoint không được bị Deployment Protection chặn.
Xóa phần "crons" trong vercel.json và redeploy để tránh hai nguồn điều phối cùng chạy.
2. Bật extension và tạo secret
Trong Supabase:
- Database → Extensions: bật pg_cron và pg_net.
- Vault: tạo hai secret sau:
Tên	Giá trị
vandao_app_url	https://TEN-MIEN-CUA-BAN
vandao_cron_secret	Giống chính xác CRON_SECRET trên Vercel
Không dùng Supabase service-role key thay cho CRON_SECRET. Không đưa secret vào frontend.
3. Tạo job ở trạng thái tắt
Chạy trong Supabase → SQL Editor:
begin;

select cron.schedule(
  'vandao-automation',
  '30 seconds',
  $job$
    select net.http_post(
      url := rtrim(
        (
          select decrypted_secret
          from vault.decrypted_secrets
          where name = 'vandao_app_url'
        ),
        '/'
      ) || '/api/v1/cron/automation',

      headers := jsonb_build_object(
        'Content-Type', 'application/json',
        'Authorization', 'Bearer ' || (
          select decrypted_secret
          from vault.decrypted_secrets
          where name = 'vandao_cron_secret'
        )
      ),

      body := '{}'::jsonb,
      timeout_milliseconds := 55000
    );
  $job$
);

select cron.alter_job(
  job_id := (
    select jobid
    from cron.job
    where jobname = 'vandao-automation'
  ),
  active := false
);

commit;
30 seconds là cú pháp hợp lệ của Supabase Cron; không phải */30 * * * * — biểu thức đó nghĩa là mỗi 30 phút.
4. Bật khi sẵn sàng
Khi bật, job có thể gửi lệnh game thật cho các tài khoản đang bật trợ lý. Kiểm tra cấu hình tiêu hao trước.
select cron.alter_job(
  job_id := (
    select jobid
    from cron.job
    where jobname = 'vandao-automation'
  ),
  active := true
);
Tắt lại bằng cùng câu lệnh, đổi thành:
active := false
5. Kiểm tra kết quả
Vào Integrations → Cron → Jobs → History, hoặc chạy:
select jobid, jobname, schedule, active
from cron.job
where jobname = 'vandao-automation';
Kiểm tra HTTP trả về:
select
  id,
  status_code,
  timed_out,
  error_msg,
  content,
  created
from net._http_response
order by created desc
limit 10;
Kết quả	Cần kiểm tra
200	Xem thêm processed; từng tài khoản vẫn có thể báo lỗi
processed: []	Không có tài khoản bật trợ lý hoặc chưa đến hạn
401	Secret không khớp hoặc Deployment Protection chặn
404	Sai domain/path hoặc deploy chưa cập nhật
Timeout / 5xx	Xem Vercel Function Logs
History báo thành công chỉ chứng minh SQL đã gửi yêu cầu vào hàng đợi, chưa chứng minh automation chạy thành công.
Nhịp này tạo khoảng 2.880 request/ngày, vẫn tính quota Vercel/Supabase. Không giảm khóa chống trùng xuống 30 giây một cách máy móc nếu vòng chạy có thể kéo dài hơn.
Tài liệu: Supabase Cron quickstart.