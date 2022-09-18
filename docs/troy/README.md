```python
import warnings

from broker_utils import gcp_utils

import main
import mock_input as mock


topic = "class-loop"

args = mock.input(max_messages=1000)

with warnings.catch_warnings():
    warnings.simplefilter("ignore", category=FutureWarning)
    for (alert_dict, attrs) in args:
        # alert_dict, attrs = next(args)
        snn_dict = main._classify_with_snn(alert_dict)
        avro = main._create_elasticc_msg(dict(alert=alert_dict, SuperNNova=snn_dict), attrs)
        gcp_utils.publish_pubsub(topic, avro, attrs=attrs)

subscrip = "class-loop"
msg_only = False
max_messages = 1
msgs = gcp_utils.pull_pubsub(
    subscription_name=subscrip, msg_only=msg_only, max_messages=max_messages,
)
msg = msgs[0]
payload = msg.message.data
publish_time = msg.message.publish_time



alert = fastavro.schemaless_reader( io.BytesIO( payload ), self.schema )
            messagebatch.append( { 'topic': msg.topic(),
                                   'msgoffset': msg.offset(),
                                   'timestamp': timestamp,
                                   'msg': alert } )
```
