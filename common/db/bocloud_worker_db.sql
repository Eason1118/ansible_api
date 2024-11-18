
/* Bocloud Worker local database schema*/

/* record requests and flask response */
CREATE TABLE IF NOT EXISTS task_requests (
  id             INTEGER PRIMARY KEY AUTOINCREMENT, --values start from 1 and auto increments
  request_data   VARCHAR(256) NOT NULL, --request boby content
  request_method VARCHAR(8)   NOT NULL, --request method: POST, GET ...
  request_head   VARCHAR(128) NOT NULL, --request header
  request_host   VARCHAR(18)  NOT NULL, --the host ip that send the request
  request_path   VARCHAR(32)  NOT NULL, --request path
  request_queue  VARCHAR(32), --refine queue string from request data, just exist at async task
  respond_code   INTEGER, --response status code
  error_message  VARCHAR(1500), --error messages
  UNIQUE (id, request_queue)
);

CREATE TABLE IF NOT EXISTS async_task_status (
  id          INTEGER PRIMARY KEY AUTOINCREMENT, --values start from 1 and auto increments
  request_id  INTEGER NOT NULL, --foreign key referencing the id in task_requests table
  status      INTEGER NOT NULL    DEFAULT 0 CHECK (status IN (0, 1, 2)), --value be 0=NEW,1=RUNNING,2=COMPLETE
  total_count INTEGER, --The count of total result.
  UNIQUE(id, request_id),
  FOREIGN KEY(request_id) REFERENCES task_requests(id)
);

CREATE TABLE IF NOT EXISTS async_task_result (
  id      INTEGER PRIMARY KEY    AUTOINCREMENT, --values start from 1 and auto increments
  task_id INTEGER       NOT NULL, --foreign key referencing the id in async_task_status table
  result  VARCHAR(1500) NOT NULL, --result for one target. if the task is playbook, a target exist multi-result
  target  VARCHAR(18)   NOT NULL, --target ip that task run
  valid   INTEGER       NOT NULL DEFAULT 1 CHECK (valid IN
                                                  (0, 1)), --task result wethere or not valid. valid: 1, unvalid: 2
  FOREIGN KEY (task_id) REFERENCES async_task_status (id)
);