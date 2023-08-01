import numpy as np
import pandas as pd
import tensorflow as tf
import os
print(tf.__version__)
import fire
from elapsedtimer import ElapsedTimer

class recommender:
    
    def __init__(self,mode,train_file,outdir,test_file=None,
                user_info_file=None,movie_info_file=None,
                batch_size=32,epochs=500,
                learning_rate=1e-3,num_hidden=50,
                display_step=5):


        self.mode = mode
        self.train_file = train_file
        self.outdir = outdir          
        self.test_file = test_file
        self.batch_size = batch_size
        self.learning_rate = learning_rate
        self.num_hidden = num_hidden
        self.epochs = epochs
        self.display_step = display_step
        self.user_info_file = user_info_file
        self.movie_info_file = movie_info_file

    
    def read_data(self):
        
        if self.mode  == 'train':
           self.train_data = np.load(self.train_file)
           self.num_ranks = self.train_data.shape[2]
           self.num_movies = self.train_data.shape[1]
           self.users = self.train_data.shape[0]
                
        else:
           self.train_df = pd.read_csv(self.train_file)
           self.test_data  = np.load(self.test_file)
           self.test_df = pd.DataFrame(self.test_data,columns=['userid','movieid','rating'])

           if self.user_info_file != None:
               self.user_info_df = pd.read_csv(self.user_info_file,sep='|',header=None)
               self.user_info_df.columns=['userid','age','gender','occupation','zipcode']

           if self.movie_info_file != None:
               self.movie_info_df = pd.read_csv(self.movie_info_file,sep='|',encoding='latin-1',header=None)
               self.movie_info_df = self.movie_info_df[[0,1]] 
               self.movie_info_df.columns = ['movieid','movie Title']
                  
                  

    
    def next_batch(self):
        while True:
            ix = np.random.choice(np.arange(self.train_data.shape[0]),self.batch_size)
            train_X  = self.train_data[ix,:,:]   
            yield train_X
        
        
    def __network(self):
        
        self.x  = tf.placeholder(tf.float32, [None,self.num_movies,self.num_ranks], name="x") 
        self.xr = tf.reshape(self.x, [-1,self.num_movies*self.num_ranks], name="xr") 
        self.W  = tf.Variable(tf.random_normal([self.num_movies*self.num_ranks,self.num_hidden], 0.01), name="W") 
        self.b_h = tf.Variable(tf.zeros([1,self.num_hidden],  tf.float32, name="b_h")) 
        self.b_v = tf.Variable(tf.zeros([1,self.num_movies*self.num_ranks],tf.float32, name="b_v")) 
        self.k = 2

## Converts the probability into discrete binary states i.e. 0 and 1 
        def sample_hidden(probs):
            return tf.floor(probs + tf.random_uniform(tf.shape(probs), 0, 1))

        def sample_visible(logits):
        
            logits = tf.reshape(logits,[-1,self.num_ranks])
            sampled_logits = tf.multinomial(logits,1)             
            sampled_logits = tf.one_hot(sampled_logits,depth = 5)
            logits = tf.reshape(logits,[-1,self.num_movies*self.num_ranks])
            print(logits)
            return logits  
    
                      

          
  
## Gibbs sampling step
        def gibbs_step(x_k):
          #  x_k = tf.reshape(x_k,[-1,self.num_movies*self.num_ranks]) 
            h_k = sample_hidden(tf.sigmoid(tf.matmul(x_k,self.W) + self.b_h))
            x_k = sample_visible(tf.add(tf.matmul(h_k,tf.transpose(self.W)),self.b_v))
            return x_k
## Run multiple gives Sampling step starting from an initital point     
        def gibbs_sample(k,x_k):
             
            for i in range(k):
                x_k = gibbs_step(x_k) 
# Returns the gibbs sample after k iterations
            return x_k

# Constrastive Divergence algorithm
# 1. Through Gibbs sampling locate a new visible state x_sample based on the current visible state x    
# 2. Based on the new x sample a new h as h_sample    
        self.x_s = gibbs_sample(self.k,self.xr) 
        self.h_s = sample_hidden(tf.sigmoid(tf.matmul(self.x_s,self.W) + self.b_h)) 

# Sample hidden states based given visible states
        self.h = sample_hidden(tf.sigmoid(tf.matmul(self.xr,self.W) + self.b_h)) 
# Sample visible states based given hidden states
        self.x_ = sample_visible(tf.matmul(self.h,tf.transpose(self.W)) + self.b_v)

# The weight updated based on gradient descent 
        #self.size_batch = tf.cast(tf.shape(x)[0], tf.float32)
        self.W_add  = tf.multiply(self.learning_rate/self.batch_size,tf.subtract(tf.matmul(tf.transpose(self.xr),self.h),tf.matmul(tf.transpose(self.x_s),self.h_s)))
        self.bv_add = tf.multiply(self.learning_rate/self.batch_size, tf.reduce_sum(tf.subtract(self.xr,self.x_s), 0, True))
        self.bh_add = tf.multiply(self.learning_rate/self.batch_size, tf.reduce_sum(tf.subtract(self.h,self.h_s), 0, True))
        self.updt = [self.W.assign_add(self.W_add), self.b_v.assign_add(self.bv_add), self.b_h.assign_add(self.bh_add)]
        
        
    def _train(self):
            
        self.__network()
# TensorFlow graph execution

        with tf.Session() as sess:
            self.saver = tf.train.Saver()
            #saver = tf.train.Saver(write_version=tf.train.SaverDef.V2)  
            # Initialize the variables of the Model
            init = tf.global_variables_initializer()
            sess.run(init)
            
            total_batches = self.train_data.shape[0]//self.batch_size
            batch_gen = self.next_batch()
            # Start the training 
            for epoch in range(self.epochs):
                if epoch < 150:
                    self.k = 2
    
                if (epoch > 150) & (epoch < 250):
                    self.k = 3
                    
                if (epoch > 250) & (epoch < 350):
                    self.k = 5
    
                if (epoch > 350) & (epoch < 500):
                    self.k = 9
                
                    # Loop over all batches
                for i in range(total_batches):
                    self.X_train = next(batch_gen)
                    # Run the weight update 
                    #batch_xs = (batch_xs > 0)*1
                    _ = sess.run([self.updt],feed_dict={self.x:self.X_train})
                    
                # Display the running step 
                if epoch % self.display_step == 0:
                    print("Epoch:", '%04d' % (epoch+1))
                    self.saver.save(sess,os.path.join(self.outdir,'model'), global_step=epoch)
           # Do the prediction for all users all items irrespective of whether they have been rated
            self.logits_pred = tf.reshape(self.x_,[self.users,self.num_movies,self.num_ranks])
            self.probs     = tf.nn.softmax(self.logits_pred,axis=2)
            out = sess.run(self.probs,feed_dict={self.x:self.train_data})
            recs = []
            for i in range(self.users):
                for j in range(self.num_movies):
                    rec = [i,j,np.argmax(out[i,j,:]) +1]
                    recs.append(rec)
            recs = np.array(recs)
            df_pred = pd.DataFrame(recs,columns=['userid','movieid','predicted_rating'])
            df_pred.to_csv(self.outdir + 'pred_all_recs.csv',index=False)
                          
            print("RBM training Completed !") 

    def inference(self):
        
        self.df_result = self.test_df.merge(self.train_df,on=['userid','movieid'])
        # in order to get the original ids we just need to add  1 
        self.df_result['userid'] = self.df_result['userid'] + 1 
        self.df_result['movieid'] = self.df_result['movieid'] + 1 
        if self.user_info_file != None:
            self.df_result = self.df_result.merge(self.user_info_df,on=['userid'])
        if self.movie_info_file != None:
            self.df_result = self.df_result.merge(self.movie_info_df,on=['movieid'])
        self.df_result.to_csv(self.outdir + 'test_results.csv',index=False)


        print(f'output written to {self.outdir}test_results.csv')
        test_rmse = (np.mean((self.df_result['rating'].values - self.df_result['predicted_rating'].values)**2))**0.5
        print(f'test RMSE : {test_rmse}')

       
    def main_process(self):
        self.read_data()

        if self.mode == 'train':
            self._train()
        else:
            self.inference()

if __name__ == '__main__':
    with ElapsedTimer('process RBM'):
        fire.Fire(recommender)
